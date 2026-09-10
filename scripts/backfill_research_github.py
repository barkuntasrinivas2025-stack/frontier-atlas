from __future__ import annotations
import argparse, asyncio, re, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp
from sqlalchemy import select
from sqlalchemy import update
from src.acquisition.pwc_links import PWCLinkIndex, normalize_arxiv_id
from src.config.settings import get_settings
from src.github.metrics import github_repo_metrics
from src.storage.database import AsyncSessionLocal
from src.storage.models import EntityRecord

ARXIV_RE = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/)?([0-9]{4}\.[0-9]{4,5})(?:v\\d+)?", re.I)

def extract_id(payload: dict) -> str:
    aid = normalize_arxiv_id(str(payload.get("arxiv_id") or ""))
    if aid: return aid
    url = str(payload.get("paper_url") or "")
    m = ARXIV_RE.search(url)
    return normalize_arxiv_id(m.group(1)) if m else ""

def args():
    p=argparse.ArgumentParser(description="Backfill existing research-paper records with PWC/GitHub metadata.")
    p.add_argument("--limit", type=int, default=0, help="0 = all research papers missing GitHub enrichment")
    p.add_argument("--concurrency", type=int, default=5)
    return p.parse_args()

async def main():
    a=args(); s=get_settings(); idx=PWCLinkIndex(); sem=asyncio.Semaphore(a.concurrency)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http, AsyncSessionLocal() as db:
        rows=list((await db.scalars(select(EntityRecord).where(EntityRecord.record_type=="research_paper").order_by(EntityRecord.id).limit(a.limit if a.limit else 1000000))).all())
        updated=matched=enriched=0
        async def enrich(url):
            async with sem:
                try:
                    return await github_repo_metrics(url, token=s.github_token or None, session=http)
                except Exception:
                    return None
        for r in rows:
            payload=dict(r.payload or {}); aid=extract_id(payload)
            if not aid: continue
            match=idx.lookup(aid)
            if not match: continue
            matched += 1
            payload["arxiv_id"]=aid; payload["github_url"]=match.repo_url
            metrics=await enrich(match.repo_url)
            if metrics is not None:
                payload["github_stars"]=int(metrics.get("stars",0)); enriched += 1
            else:
                payload.setdefault("github_stars", None)
            await db.execute(update(EntityRecord).where(EntityRecord.id==r.id).values(payload=payload))
            updated += 1
            if updated % 25 == 0:
                await db.commit(); print({"updated":updated,"pwc_matched":matched,"github_enriched":enriched})
        await db.commit(); print({"selected":len(rows),"updated":updated,"pwc_matched":matched,"github_enriched":enriched})

if __name__ == "__main__":
    if sys.platform=="win32": asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else: asyncio.run(main())
