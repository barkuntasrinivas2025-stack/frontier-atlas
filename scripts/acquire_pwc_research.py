from __future__ import annotations

import argparse
import asyncio
import random
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.acquisition.pwc_links import PWCLinkIndex, normalize_arxiv_id
from src.config.settings import get_settings
from src.extraction.schemas import ResearchPaper
from src.github.metrics import GitHubMetricsClient
from src.storage.database import AsyncSessionLocal
from src.storage.models import EntityRecord, RawDocument

ATOM = "http://www.w3.org/2005/Atom"
ARXIV_API = "https://export.arxiv.org/api/query"
UA = "FrontierAtlas/1.0"
DEFAULT_DELAY = 5.0


def parse_args():
    p = argparse.ArgumentParser(description="Build a PWC-backed research-paper set with current GitHub metrics.")
    p.add_argument("--target", type=int, default=1000)
    p.add_argument("--candidate-limit", type=int, default=1800)
    p.add_argument("--batch-size", type=int, default=25)
    p.add_argument("--arxiv-delay", type=float, default=DEFAULT_DELAY)
    p.add_argument("--github-concurrency", type=int, default=5)
    p.add_argument("--max-retries", type=int, default=8)
    return p.parse_args()


def txt(e, tag):
    n = e.find(f"{{{ATOM}}}{tag}")
    return (n.text or "").strip() if n is not None and n.text else ""


def parse_dt(value):
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_entries(xml):
    root = ET.fromstring(xml)
    out = {}
    for e in root.findall(f"{{{ATOM}}}entry"):
        url = txt(e, "id")
        aid = normalize_arxiv_id(url)
        if not aid:
            continue
        authors = []
        for a in e.findall(f"{{{ATOM}}}author"):
            n = a.find(f"{{{ATOM}}}name")
            if n is not None and n.text:
                authors.append(n.text.strip())
        out[aid] = {
            "title": " ".join(txt(e, "title").split()),
            "abstract": " ".join(txt(e, "summary").split()),
            "authors": authors,
            "published_at": parse_dt(txt(e, "published")),
            "paper_url": url,
        }
    return out


async def fetch_arxiv_batch(http, ids, delay, max_retries):
    params = {"id_list": ",".join(ids), "max_results": len(ids)}
    for attempt in range(max_retries):
        if attempt == 0:
            await asyncio.sleep(delay)
        try:
            async with http.get(
                ARXIV_API,
                params=params,
                headers={"User-Agent": UA},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                if r.status in {408, 425, 429, 500, 502, 503, 504}:
                    retry_after = r.headers.get("Retry-After")
                    try:
                        wait = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        wait = 0.0
                    wait = max(wait, min(60.0, 3.0 * (2 ** attempt)))
                    wait += random.uniform(0, 1.5)
                    print(f"ArXiv HTTP {r.status}; retry {attempt + 1}/{max_retries} in {wait:.1f}s", flush=True)
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return parse_entries(await r.text())
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            wait = min(60.0, 3.0 * (2 ** attempt)) + random.uniform(0, 1.5)
            print(f"ArXiv error; retry {attempt + 1}/{max_retries} in {wait:.1f}s: {exc}", flush=True)
            await asyncio.sleep(wait)
    return {}


async def main():
    args = parse_args()
    settings = get_settings()
    index = PWCLinkIndex()

    # The PWC snapshot is historical, so we deliberately select only papers
    # with an explicit PWC paper↔code relationship and an ArXiv ID.
    parquet = index.path
    import pyarrow.parquet as pq
    table = pq.read_table(parquet, columns=["paper_arxiv_id", "repo_url", "is_official"])
    rows = table.to_pylist()

    candidates = []
    seen = set()
    for row in rows:
        aid = normalize_arxiv_id(row.get("paper_arxiv_id") or "")
        repo = (row.get("repo_url") or "").strip()
        if not aid or not repo or not row.get("is_official"):
            continue
        if aid in seen:
            continue
        seen.add(aid)
        candidates.append((aid, repo))
        if len(candidates) >= args.candidate_limit:
            break

    print(f"PWC official ArXiv candidates: {len(candidates)}", flush=True)

    settings = get_settings()
    connector = aiohttp.TCPConnector(limit=5)
    timeout = aiohttp.ClientTimeout(total=60)
    headers = {"User-Agent": UA, "Accept": "application/atom+xml"}

    processed = 0
    github_enriched = 0
    skipped = 0
    offset = 0

    async with aiohttp.ClientSession(connector=connector, timeout=timeout, headers=headers) as http:
        gh = GitHubMetricsClient(
            token=settings.github_token or None,
            concurrency=args.github_concurrency,
            timeout_seconds=30,
        )

        while offset < len(candidates) and processed < args.target:
            batch = candidates[offset : offset + args.batch_size]
            offset += len(batch)

            metadata = await fetch_arxiv_batch(
                http,
                [aid for aid, _ in batch],
                args.arxiv_delay,
                args.max_retries,
            )
            if not metadata:
                print(f"batch skipped; progress {processed}/{args.target}", flush=True)
                continue

            for aid, repo_url in batch:
                if processed >= args.target:
                    break
                meta = metadata.get(aid)
                if not meta:
                    skipped += 1
                    continue

                metrics = await gh.get_repo(repo_url, session=http)
                if not metrics:
                    skipped += 1
                    continue

                collected = datetime.now(timezone.utc)
                payload = {
                    "title": meta["title"],
                    "arxiv_id": aid,
                    "abstract": meta["abstract"],
                    "authors": meta["authors"],
                    "paper_url": meta["paper_url"],
                    "published_at": meta["published_at"],
                    "github_url": repo_url,
                    "github_stars": metrics.get("stars"),
                    "source": {
                        "source_url": meta["paper_url"],
                        "source_name": "arxiv+pwc+github",
                        "collected_at": collected,
                        "content_hash": None,
                    },
                }

                # Validate before persistence: no fabricated paper or GitHub data.
                paper = ResearchPaper.model_validate(payload)
                payload = paper.model_dump(mode="json")

                async with AsyncSessionLocal() as session:
                    raw = {
                        "url": meta["paper_url"],
                        "source_name": "arxiv",
                        "content_type": "application/atom+xml",
                        "http_status": 200,
                        "raw_html": None,
                        "extracted_text": f'{meta["title"]}\n\n{meta["abstract"]}',
                        "content_hash": None,
                        "discovered_at": collected,
                        "collected_at": collected,
                        "metadata_json": {"arxiv_id": aid, "pwc_repo_url": repo_url},
                        "processed": True,
                    }
                    stmt = insert(RawDocument).values(**raw).on_conflict_do_update(
                        index_elements=["url"],
                        set_={
                            "collected_at": collected,
                            "processed": True,
                            "metadata_json": raw["metadata_json"],
                        },
                    )
                    await session.execute(stmt)

                    entity = {
                        "record_type": "research_paper",
                        "source_name": "arxiv+pwc+github",
                        "source_url": meta["paper_url"],
                        "schema_version": "1.0",
                        "canonical_name": meta["title"],
                        "payload": payload,
                        "source_content_hash": None,
                        "collected_at": collected,
                        "created_at": collected,
                    }
                    stmt = insert(EntityRecord).values(**entity).on_conflict_do_update(
                        constraint="uq_entity_source",
                        set_={
                            "payload": payload,
                            "canonical_name": meta["title"],
                            "collected_at": collected,
                        },
                    )
                    await session.execute(stmt)
                    await session.commit()

                processed += 1
                github_enriched += 1

            print(
                {
                    "candidate_offset": offset,
                    "research_papers_with_github": processed,
                    "github_enriched": github_enriched,
                    "skipped": skipped,
                },
                flush=True,
            )

    print(
        {
            "target": args.target,
            "research_papers_with_github": processed,
            "github_enriched": github_enriched,
            "skipped": skipped,
        },
        flush=True,
    )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
