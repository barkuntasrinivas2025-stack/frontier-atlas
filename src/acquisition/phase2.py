from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import json
import re
import xml.etree.ElementTree as ET

import aiohttp
from bs4 import BeautifulSoup

from src.crawlers.phase2_sources import NEWS_SOURCES, JOB_SOURCES
from src.extraction.schemas import NewsArticle, Job, SourceProvenance
from src.freshness.dates import parse_publication_date, is_within_previous_24h
from src.freshness.dedup import canonical_url, sha256_text
from src.utils.http import HTTPClient
from src.crawlers.web import extract_fulltext, is_anti_bot_page, needs_js_render


@dataclass
class Stats:
    discovered: int = 0
    fresh: int = 0
    emitted: int = 0
    rejected_stale: int = 0
    rejected_no_date: int = 0
    duplicate: int = 0
    failed: int = 0
    fulltext_failed: int = 0
    by_source: dict = field(default_factory=dict)


def _clean(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return " ".join(BeautifulSoup(value, "lxml").stripped_strings)


def _first_value(mapping, *keys):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _extract_job_fields(text):
    """Best-effort extraction from feed/API descriptions without inventing values."""
    clean = _clean(text) or ""
    company = None
    location = None

    company_patterns = [
        r"(?:company|employer|organization)\s*[:\-]\s*([^|•\n]+)",
        r"(?:at|by)\s+([A-Z][A-Za-z0-9&.,' -]{2,80})",
    ]
    location_patterns = [
        r"(?:location|locations|city|where)\s*[:\-]\s*([^|•\n]+)",
    ]

    for pattern in company_patterns:
        m = re.search(pattern, clean, flags=re.I)
        if m:
            candidate = m.group(1).strip(" -|•")
            if candidate and len(candidate) <= 120:
                company = candidate
                break

    for pattern in location_patterns:
        m = re.search(pattern, clean, flags=re.I)
        if m:
            candidate = m.group(1).strip(" -|•")
            if candidate and len(candidate) <= 160:
                location = candidate
                break

    return company, location


def parse_feed(body, source, now):
    """Parse XML RSS/Atom feeds, including common namespace variants."""
    root = ET.fromstring(body)
    rows = []

    for item in root.iter():
        if not item.tag.lower().endswith(("item", "entry")):
            continue

        def val(keys):
            for k in keys:
                e = next(
                    (x for x in list(item) if x.tag.lower().endswith(k)),
                    None,
                )
                if e is None:
                    continue
                href = e.attrib.get("href")
                value = href if href else e.text
                if value:
                    return value
            return None

        title = val(["title"])
        url = val(["link"])
        date = val(["pubdate", "published", "updated", "date"])
        desc = val(["description", "summary", "content"])

        if not title or not url:
            continue

        text = f"{title} {desc or ''}".lower()
        if source.keywords and not any(k.lower() in text for k in source.keywords):
            continue

        dt = parse_publication_date(date, now=now)
        company, location = _extract_job_fields(desc)

        rows.append(
            {
                "title": _clean(title),
                "url": url.strip(),
                "summary": _clean(desc),
                "description": _clean(desc),
                "published_at": dt,
                "company": company,
                "location": location,
            }
        )

    return rows


def parse_arbeitnow_json(body, source, now):
    """Parse Arbeitnow's JSON job API without assuming XML."""
    payload = json.loads(body)
    items = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue

        title = _first_value(item, "title", "job_title", "position")
        url = _first_value(item, "url", "job_url", "slug")
        description = _first_value(item, "description", "summary", "snippet")
        company = _first_value(item, "company_name", "company", "employer")
        location = _first_value(item, "location", "locations", "city")

        # Arbeitnow may expose the publication time under different fields.
        raw_date = _first_value(
            item,
            "published_at",
            "published",
            "created_at",
            "created",
            "date",
        )

        if not title or not url:
            continue

        text = f"{title} {description or ''} {company or ''}".lower()
        if source.keywords and not any(k.lower() in text for k in source.keywords):
            continue

        if isinstance(location, list):
            location = ", ".join(str(x) for x in location)
        if isinstance(company, dict):
            company = _first_value(company, "name", "title")

        dt = parse_publication_date(raw_date, now=now)

        # If API data omitted fields, make a conservative best effort from
        # the description; never invent a company/location.
        fallback_company, fallback_location = _extract_job_fields(description)
        company = company or fallback_company
        location = location or fallback_location

        rows.append(
            {
                "title": _clean(title),
                "url": url.strip(),
                "summary": _clean(description),
                "description": _clean(description),
                "published_at": dt,
                "company": _clean(company),
                "location": _clean(location),
            }
        )

    return rows


async def _fetch_text(http, url):
    try:
        status, body, _ = await http.get(url, allow_redirects=True)
        if status != 200:
            return None
        return body
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None

def _fulltext(html):
    soup = BeautifulSoup(html, "lxml")
    for x in soup(["script", "style", "nav", "footer", "noscript"]):
        x.decompose()

    main = soup.find("article") or soup.find("main") or soup.body or soup
    return " ".join(main.stripped_strings)



def _effective_source_urls(source):
    name = source.name.lower()
    if "venturebeat" in name:
        # VentureBeat's AI category page is live, but its category RSS endpoint
        # can intermittently reject automated requests. Fall back to the
        # publisher's main RSS feed; the source keyword filter keeps only AI items.
        return [
            "https://venturebeat.com/category/ai/feed/",
            "https://feeds.venturebeat.com/VentureBeat",
            "http://feeds.venturebeat.com/VentureBeat",
        ]
    if "remote ok" in name:
        return ["https://remoteok.com/api"]
    return [source.url]


def _extract_meta_date(html, now):
    soup = BeautifulSoup(html, "lxml")
    candidates = []

    for tag in soup.find_all("meta"):
        key = (
            tag.get("property")
            or tag.get("name")
            or tag.get("itemprop")
            or ""
        ).lower()
        value = tag.get("content")
        if not value:
            continue
        if any(
            token in key
            for token in (
                "article:published_time",
                "article:modified_time",
                "publish",
                "published",
                "datepublished",
                "datecreated",
                "timestamp",
            )
        ):
            candidates.append(value)

    for tag in soup.find_all("time"):
        value = tag.get("datetime") or tag.get_text(" ", strip=True)
        if value:
            candidates.append(value)

    for value in candidates:
        try:
            parsed = parse_publication_date(value, now=now)
            if parsed:
                return parsed
        except Exception:
            continue
    return None


def _parse_remoteok_json(body, source, now):
    payload = json.loads(body)
    if not isinstance(payload, list):
        return []

    rows = []
    for item in payload:
        if not isinstance(item, dict) or "legal" in item:
            continue

        title = item.get("position") or item.get("title")
        url = item.get("url") or item.get("apply_url")
        company = item.get("company")
        location = item.get("location")
        description = item.get("description")
        tags = item.get("tags") or []

        if not title or not url:
            continue

        haystack = " ".join(
            str(x) for x in [title, description, company, *tags] if x
        ).lower()
        if source.keywords and not any(k.lower() in haystack for k in source.keywords):
            continue

        raw_date = (
            item.get("date")
            or item.get("publication_date")
            or item.get("published_at")
            or item.get("last_updated")
        )

        # Remote OK may expose Unix timestamps.
        if isinstance(raw_date, (int, float)):
            parsed = datetime.fromtimestamp(raw_date, tz=timezone.utc)
        else:
            parsed = parse_publication_date(raw_date, now=now)

        rows.append({
            "title": _clean(title),
            "url": str(url).strip(),
            "summary": _clean(description),
            "description": _clean(description),
            "published_at": parsed,
            "company": _clean(company),
            "location": _clean(location),
        })
    return rows


async def collect_phase2(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stats = Stats()
    news = []
    jobs = []
    seen_urls = set()
    seen_content = set()

    settings = __import__("src.config.settings", fromlist=["get_settings"]).get_settings()

    async with HTTPClient(
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=5,
        concurrency=settings.crawler_concurrency,
    ) as http:
        source_sem = asyncio.Semaphore(settings.crawler_concurrency)

        async def fetch_source(source):
            async with source_sem:
                return source

        for source in [*NEWS_SOURCES, *JOB_SOURCES]:
            stats.by_source[source.name] = {
                "discovered": 0,
                "fresh": 0,
                "emitted": 0,
                "failed": 0,
            }

            try:
                source_urls = _effective_source_urls(source)
                body = None
                content_type = ""
                source_name_lower = source.name.lower()

                for source_url in source_urls:
                    try:
                        status, candidate_body, response_headers = await http.get(
                            source_url,
                            allow_redirects=True,
                        )
                        if status == 200:
                            body = candidate_body
                            content_type = response_headers.get(
                                "Content-Type", ""
                            ).lower()
                            break
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        continue

                if body is None:
                    stats.failed += 1
                    stats.by_source[source.name]["failed"] += 1
                    continue

                if "remote ok" in source_name_lower:
                    try:
                        rows = _parse_remoteok_json(body, source, now)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        rows = []
                elif "arbeitnow" in source_name_lower or "json" in content_type:
                    try:
                        rows = parse_arbeitnow_json(body, source, now)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        rows = parse_feed(body, source, now)
                else:
                    rows = parse_feed(body, source, now)

                stats.discovered += len(rows)
                stats.by_source[source.name]["discovered"] = len(rows)

                for row in rows:
                    dt = row["published_at"]

                    if not dt:
                        try:
                            date_status, date_html, _ = await http.get(
                                row["url"],
                                allow_redirects=True,
                            )
                            if date_status == 200:
                                dt = _extract_meta_date(date_html, now)
                                row["published_at"] = dt
                        except (aiohttp.ClientError, asyncio.TimeoutError):
                            pass

                    if not dt:
                        stats.rejected_no_date += 1
                        continue

                    if not is_within_previous_24h(dt, now=now):
                        stats.rejected_stale += 1
                        continue

                    url = canonical_url(row["url"])
                    if not url or url in seen_urls:
                        stats.duplicate += 1
                        continue

                    seen_urls.add(url)
                    stats.fresh += 1
                    stats.by_source[source.name]["fresh"] += 1

                    prov = SourceProvenance(
                        source_url=url,
                        source_name=source.name,
                        collected_at=now,
                    )

                    if source.kind == "news":
                        content = None
                        try:
                            page_status, page_html, _ = await http.get(
                                url,
                                allow_redirects=True,
                            )
                            if page_status == 200 and not is_anti_bot_page(page_html):
                                content = extract_fulltext(page_html)
                        except (aiohttp.ClientError, asyncio.TimeoutError):
                            stats.fulltext_failed += 1

                        if not content:
                            # The source item itself remains traceable, but a
                            # news record without fetched body is not emitted.
                            stats.fulltext_failed += 1
                            continue

                        content_hash = sha256_text(content)
                        if content_hash in seen_content:
                            stats.duplicate += 1
                            continue
                        seen_content.add(content_hash)

                        obj = NewsArticle(
                            title=row["title"],
                            url=url,
                            summary=row["summary"],
                            content=content,
                            published_at=dt,
                            source=prov,
                        )
                        news.append(obj)

                    else:
                        description = row["description"]
                        company = row.get("company")
                        location = row.get("location")

                        # Fetch the job page when the feed/API does not give a
                        # usable description. This is full-text crawling for
                        # job sources while preserving the source URL.
                        if not description or len(description) < 80:
                            try:
                                page_status, page_html, _ = await http.get(
                                    url,
                                    allow_redirects=True,
                                )
                                if page_status == 200 and not is_anti_bot_page(page_html):
                                    description = extract_fulltext(page_html)
                            except (aiohttp.ClientError, asyncio.TimeoutError):
                                pass

                        fallback_company, fallback_location = _extract_job_fields(description)
                        company = company or fallback_company
                        location = location or fallback_location

                        obj = Job(
                            title=row["title"],
                            company=company,
                            location=location,
                            url=url,
                            description=description,
                            published_at=dt,
                            source=prov,
                        )
                        jobs.append(obj)

                    stats.emitted += 1
                    stats.by_source[source.name]["emitted"] += 1

            except Exception as exc:
                stats.failed += 1
                stats.by_source[source.name]["failed"] += 1
                print(f"Phase II source failed: {source.name}: {exc}", flush=True)

    return news, jobs, stats
