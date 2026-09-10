from __future__ import annotations

import asyncio
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import pandas as pd

from src.config.settings import get_settings
from src.extraction.schemas import Product, SourceProvenance, Startup
from src.resolution.resolver import EntityResolver
from src.resolution.seed import DEFAULT_SEED
from src.storage.database import AsyncSessionLocal
from src.storage.entity_records import upsert_entity


YC_DATASET_URL = (
    "https://huggingface.co/datasets/"
    "jeffboudier/yc-companies-august-2025/resolve/main/"
    "yc-companies-august-2025.csv"
)

# Public dataset documented by the Product Hunt ETL project:
# https://github.com/maneshkarun/producthunt-products-etl
#
# Kaggle dataset:
# maneshkarun/producthunt-products-dataset-2014-2021
PRODUCT_HUNT_KAGGLE_API = (
    "https://www.kaggle.com/api/v1/datasets/download/"
    "maneshkarun/producthunt-products-dataset-2014-2021"
)

DATA_DIR = Path("data/processed")
YC_FILE = DATA_DIR / "yc-companies-august-2025.csv"
PH_ZIP = DATA_DIR / "producthunt-products-dataset-2014-2021.zip"


async def download(
    session: aiohttp.ClientSession,
    url: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading: {url}")

    async with session.get(url, allow_redirects=True) as response:
        if response.status != 200:
            raise RuntimeError(
                f"Download failed: HTTP {response.status}: {url}"
            )

        data = await response.read()

    destination.write_bytes(data)

    print(
        f"Downloaded {destination} "
        f"({destination.stat().st_size:,} bytes)"
    )


def load_yc_startups(path: Path) -> list[Startup]:
    df = pd.read_csv(path)

    records: list[Startup] = []
    seen: set[str] = set()

    collected_at = datetime.now(timezone.utc)

    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()

        if not name or name.lower() == "nan":
            continue

        source_url = str(row.get("url", "")).strip()

        if not source_url or source_url.lower() == "nan":
            slug = str(row.get("slug", "")).strip()
            if not slug or slug.lower() == "nan":
                continue
            source_url = (
                f"https://www.ycombinator.com/companies/{slug}"
            )

        if source_url in seen:
            continue

        seen.add(source_url)

        description = row.get("long_description")
        if pd.isna(description) or not str(description).strip():
            description = row.get("one_liner")

        website = row.get("website")
        if pd.isna(website):
            website = None
        else:
            website = str(website).strip()

            # Normalize bare domains while rejecting empty/malformed values.
            if not website or website in {"http://", "https://", "nan", "None"}:
                website = None
            else:
                if not website.startswith(("http://", "https://")):
                    website = "https://" + website

                # Pydantic HttpUrl needs a real host.
                try:
                    from pydantic import TypeAdapter
                    from pydantic_core import PydanticCustomError
                    TypeAdapter(__import__("pydantic").HttpUrl).validate_python(
                        website
                    )
                except Exception:
                    website = None

        # Do not infer a company's founding year from its YC batch.
        # The batch year is not necessarily the legal/company founding year.
        founded_year = None

        records.append(
            Startup(
                name=name,
                description=(
                    str(description).strip()
                    if description is not None
                    and not pd.isna(description)
                    else None
                ),
                website=(
                    str(website).strip()
                    if website is not None
                    and not pd.isna(website)
                    else None
                ),
                founded_year=founded_year,
                funding=None,
                source=SourceProvenance(
                    source_url=source_url,
                    source_name="yc_oss_api_snapshot_2025",
                    collected_at=collected_at,
                ),
            )
        )

    return records


def find_product_csv(extract_dir: Path) -> Path:
    csv_files = list(extract_dir.rglob("*.csv"))

    if not csv_files:
        raise RuntimeError(
            "Product Hunt archive did not contain a CSV file"
        )

    # Prefer a file whose name resembles the known dataset.
    preferred = [
        p for p in csv_files
        if "product" in p.name.lower()
        or "hunt" in p.name.lower()
    ]

    return preferred[0] if preferred else csv_files[0]


def load_product_hunt(path: Path) -> list[Product]:
    extract_dir = path.parent / "producthunt_dataset"

    if extract_dir.exists():
        import shutil
        shutil.rmtree(extract_dir)

    import zipfile

    with zipfile.ZipFile(path) as zf:
        zf.extractall(extract_dir)

    csv_path = find_product_csv(extract_dir)

    print(f"Reading Product Hunt dataset: {csv_path}")

    df = pd.read_csv(
        csv_path,
        low_memory=False,
    )

    records: list[Product] = []
    seen: set[str] = set()

    collected_at = datetime.now(timezone.utc)

    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()

        if not name or name.lower() == "nan":
            continue

        source_url = str(row.get("_id", "")).strip()

        if not source_url or source_url.lower() == "nan":
            continue

        if source_url.startswith("/"):
            source_url = (
                "https://www.producthunt.com" + source_url
            )

        if not source_url.startswith("http"):
            continue

        if source_url in seen:
            continue

        seen.add(source_url)

        description = row.get("product_description")
        if pd.isna(description):
            description = None

        website = row.get("websites")
        if pd.isna(website):
            website = None
        else:
            website = str(website).strip()

            if not website or website in {"nan", "None", "[]"}:
                website = None
            else:
                # Product Hunt archive stores this field in several forms:
                # plain URL, Python-list-like string, or multiple URLs.
                import ast
                import re

                candidates = []

                try:
                    parsed = ast.literal_eval(website)
                    if isinstance(parsed, list):
                        candidates.extend(str(x).strip() for x in parsed)
                    elif isinstance(parsed, str):
                        candidates.append(parsed.strip())
                except (ValueError, SyntaxError):
                    candidates.append(website)

                if not candidates:
                    candidates = re.findall(
                        r"https?://[^\\s\\]\\\"']+",
                        website,
                    )

                valid_website = None

                from pydantic import HttpUrl, TypeAdapter

                adapter = TypeAdapter(HttpUrl)

                for candidate in candidates:
                    candidate = candidate.strip().strip("[]'\\\"")

                    if not candidate.startswith(("http://", "https://")):
                        continue

                    try:
                        adapter.validate_python(candidate)
                        valid_website = candidate
                        break
                    except Exception:
                        continue

                website = valid_website

        category = row.get("category_tags")
        if pd.isna(category):
            category = None

        records.append(
            Product(
                name=name,
                description=(
                    str(description).strip()
                    if description is not None
                    else None
                ),
                website=(
                    str(website).strip()
                    if website is not None
                    else None
                ),
                category=(
                    str(category).strip()
                    if category is not None
                    else None
                ),
                company_name=None,
                source=SourceProvenance(
                    source_url=source_url,
                    source_name="product_hunt_archive_2014_2021",
                    collected_at=collected_at,
                ),
            )
        )

    return records


async def persist(
    records,
    record_type: str,
    resolver: EntityResolver,
) -> int:
    count = 0

    async with AsyncSessionLocal() as session:
        for record in records:
            name = getattr(
                record,
                "name",
                getattr(record, "title", ""),
            )

            resolution = resolver.resolve(name)

            await upsert_entity(
                session,
                record_type,
                record.source.source_name,
                str(record.source.source_url),
                record.model_dump(mode="json"),
                resolution.canonical_name,
            )

            count += 1

        await session.commit()

    return count


async def main() -> None:
    settings = get_settings()

    timeout = aiohttp.ClientTimeout(
        total=max(settings.http_timeout_seconds, 120)
    )

    headers = {
        "User-Agent": (
            "FrontierAtlas/1.0 "
            "(+https://github.com/"
            "barkuntasrinivas2025-stack/frontier-atlas)"
        )
    }

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=headers,
    ) as session:

        if not YC_FILE.exists():
            await download(
                session,
                YC_DATASET_URL,
                YC_FILE,
            )

        if not PH_ZIP.exists():
            await download(
                session,
                PRODUCT_HUNT_KAGGLE_API,
                PH_ZIP,
            )

    print("Loading YC startup dataset...")
    startups = load_yc_startups(YC_FILE)

    print("Loading Product Hunt dataset...")
    products = load_product_hunt(PH_ZIP)

    print(f"Unique startups: {len(startups)}")
    print(f"Unique products: {len(products)}")

    if len(startups) < 1000:
        raise RuntimeError(
            f"Startup target not met: {len(startups)}"
        )

    if len(products) < 1000:
        raise RuntimeError(
            f"Product target not met: {len(products)}"
        )

    resolver = EntityResolver(DEFAULT_SEED)

    startup_count = await persist(
        startups,
        "startup",
        resolver,
    )

    product_count = await persist(
        products,
        "product",
        resolver,
    )

    print()
    print("Phase I startup/product acquisition complete")
    print(
        {
            "startups_persisted": startup_count,
            "products_persisted": product_count,
        }
    )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(
            main(),
            loop_factory=asyncio.SelectorEventLoop,
        )
    else:
        asyncio.run(main())
