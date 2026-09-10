from __future__ import annotations
import argparse, asyncio, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from src.acquisition.pwc_links import PWCLinkIndex, normalize_arxiv_id
from src.config.settings import get_settings
from src.github.metrics import GitHubMetricsClient
from src.extraction.schemas import ResearchPaper
from src.storage.database import AsyncSessionLocal
from src.storage.models import EntityRecord

async def main():
    p=argparse.ArgumentParser(); p.add_argument('--limit',type=int,default=20); p.add_argument('--concurrency',type=int,default=3); a=p.parse_args()
    settings=get_settings(); idx=PWCLinkIndex(); gh=GitHubMetricsClient(settings.github_token, a.concurrency)
    async with AsyncSessionLocal() as db:
        rows=list(await db.scalars(select(EntityRecord).where(EntityRecord.record_type=='research_paper').order_by(EntityRecord.id).limit(a.limit)))
        matched=updated=enriched=0
        for r in rows:
            payload=dict(r.payload); aid=normalize_arxiv_id(payload.get('arxiv_id') or payload.get('paper_url',''))
            link=idx.lookup(aid)
            if not link: continue
            matched+=1
            m=await gh.get_repo(link.repo_url)
            payload['arxiv_id']=aid; payload['github_url']=link.repo_url
            if m: payload['github_stars']=m['stars']; enriched+=1
            else: payload['github_stars']=None
            await db.execute(update(EntityRecord).where(EntityRecord.id==r.id).values(payload=payload, collected_at=r.collected_at, created_at=r.created_at))
            updated+=1
        await db.commit()
    print({'selected':len(rows),'updated':updated,'pwc_matched':matched,'github_enriched':enriched})
if __name__=='__main__': asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop) if sys.platform=='win32' else asyncio.run(main())
