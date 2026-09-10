from __future__ import annotations
import argparse, asyncio, sys, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aiohttp
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from src.acquisition.pwc_links import PWCLinkIndex
from src.config.settings import get_settings
from src.extraction.schemas import ResearchPaper
from src.github.metrics import GitHubMetricsClient
from src.resolution.resolver import EntityResolver
from src.resolution.seed import DEFAULT_SEED
from src.storage.database import AsyncSessionLocal
from src.storage.models import EntityMapping, EntityRecord, RawDocument
ATOM='http://www.w3.org/2005/Atom'; ARXIV_API='https://export.arxiv.org/api/query'; UA='FrontierAtlas/1.0'
def parse_args():
 p=argparse.ArgumentParser(); p.add_argument('--limit',type=int,default=0); p.add_argument('--batch-size',type=int,default=25); p.add_argument('--concurrency',type=int,default=5); p.add_argument('--github-concurrency',type=int,default=5); p.add_argument('--arxiv-delay',type=float,default=5.0); return p.parse_args()
def txt(e,t):
 n=e.find(f'{{{ATOM}}}{t}'); return (n.text or '').strip() if n is not None else ''
def dt(v):
 if not v:return None
 x=datetime.fromisoformat(v.replace('Z','+00:00')); return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
def parse_entries(xml):
 root=ET.fromstring(xml); out={}
 for e in root.findall(f'{{{ATOM}}}entry'):
  url=txt(e,'id'); aid=url.rsplit('/',1)[-1]
  if not aid: continue
  authors=[]
  for a in e.findall(f'{{{ATOM}}}author'):
   n=a.find(f'{{{ATOM}}}name')
   if n is not None and n.text: authors.append(n.text.strip())
  out[aid]={'title':' '.join(txt(e,'title').split()),'abstract':' '.join(txt(e,'summary').split()),'authors':authors,'published_at':dt(txt(e,'published')),'paper_url':url}
 return out
async def fetch_arxiv_batch(http, ids, delay, max_retries=8):
    """Fetch an ArXiv batch with conservative throttling and retry handling.

    A single exhausted batch is returned as an empty list rather than
    terminating the whole ingestion run. This makes processing resumable:
    the raw record remains unprocessed and can be retried later.
    """
    import random

    url = "https://export.arxiv.org/api/query"
    params = {"id_list": ",".join(ids), "max_results": len(ids)}
    last_error = None

    for attempt in range(max_retries):
        if attempt == 0:
            await asyncio.sleep(max(0.0, delay))
        try:
            async with http.get(url, params=params) as response:
                if response.status in {408, 425, 429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait = float(retry_after)
                        except ValueError:
                            wait = 0.0
                    else:
                        wait = 0.0

                    # Conservative fallback: 3, 6, 12, ... seconds, capped.
                    wait = max(wait, min(60.0, 3.0 * (2 ** attempt)))
                    wait += random.uniform(0.0, 1.5)
                    last_error = f"HTTP {response.status}"
                    print(
                        f"ArXiv throttled ({response.status}); "
                        f"retry {attempt + 1}/{max_retries} in {wait:.1f}s",
                        flush=True,
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                body = await response.text()
                return parse_entries(body)

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = str(exc)
            wait = min(60.0, 3.0 * (2 ** attempt)) + random.uniform(0.0, 1.5)
            print(
                f"ArXiv request error; retry {attempt + 1}/{max_retries} "
                f"in {wait:.1f}s: {exc}",
                flush=True,
            )
            await asyncio.sleep(wait)

    print(
        f"ArXiv batch skipped after {max_retries} retries: {last_error}",
        flush=True,
    )
    return []

async def main():
 a=parse_args(); s=get_settings(); resolver=EntityResolver(DEFAULT_SEED); pwc=PWCLinkIndex(); gh=GitHubMetricsClient(s.github_token or None,concurrency=a.github_concurrency); timeout=aiohttp.ClientTimeout(total=45)
 processed=upserted=enriched=pwc_matched=0
 async with aiohttp.ClientSession(timeout=timeout) as http, AsyncSessionLocal() as db:
  rows=list(await db.scalars(select(RawDocument).where(RawDocument.source_name=='arxiv',RawDocument.processed.is_(False)).order_by(RawDocument.id).limit(a.limit if a.limit>0 else 1000000)))
  for start in range(0,len(rows),a.batch_size):
   batch=rows[start:start+a.batch_size]; ids=[str((r.metadata_json or {}).get('arxiv_id') or '') for r in batch]; ids=[x for x in ids if x]
   details=await fetch_arxiv_batch(http,ids,a.arxiv_delay)
   for raw in batch:
    aid=str((raw.metadata_json or {}).get('arxiv_id') or ''); d=details.get(aid)
    if not d: continue
    link=pwc.lookup(aid); github_url=link.repo_url if link else None
    if link: pwc_matched+=1
    stars=None
    if github_url:
     metrics=await gh.get_repo(github_url,http)
     if metrics: stars=int(metrics['stars']); enriched+=1
    paper=ResearchPaper(title=str(d['title']),authors=list(d['authors']),abstract=str(d['abstract']),published_at=d['published_at'],arxiv_id=aid,paper_url=str(d['paper_url']),github_url=github_url,github_stars=stars,source={'source_url':str(d['paper_url']),'source_name':'arxiv','collected_at':raw.collected_at or raw.discovered_at,'content_hash':raw.content_hash})
    resolution=resolver.resolve(paper.title); payload=paper.model_dump(mode='json'); now=datetime.now(timezone.utc)
    stmt=insert(EntityRecord).values(record_type='research_paper',source_name='arxiv',source_url=str(paper.paper_url),schema_version='1.0',canonical_name=paper.title,payload=payload,source_content_hash=raw.content_hash,collected_at=raw.collected_at or raw.discovered_at,created_at=now).on_conflict_do_update(constraint='uq_entity_source',set_={'payload':payload,'canonical_name':paper.title,'source_content_hash':raw.content_hash,'collected_at':raw.collected_at or raw.discovered_at})
    await db.execute(stmt); await db.execute(insert(EntityMapping).values(raw_name=resolution.raw_name,normalized_name=resolution.normalized_name,canonical_name=resolution.canonical_name,entity_type='research_paper',match_method=resolution.method,confidence=resolution.confidence,created_at=now).on_conflict_do_nothing()); await db.execute(update(RawDocument).where(RawDocument.id==raw.id).values(processed=True)); processed+=1; upserted+=1
   await db.commit(); print({'batch_end':min(start+a.batch_size,len(rows)),'processed':processed,'pwc_matched':pwc_matched,'github_enriched':enriched})
 print({'raw_selected':len(rows),'processed':processed,'entity_records_upserted':upserted,'pwc_matched':pwc_matched,'github_enriched':enriched})
if __name__=='__main__': asyncio.run(main(),loop_factory=asyncio.SelectorEventLoop) if sys.platform=='win32' else asyncio.run(main())
