import gzip,json
from pathlib import Path
from datetime import datetime
from src.extraction.schemas import ResearchPaper,SourceProvenance
async def iter_json_records(path:Path):
 def gen():
  opener=gzip.open if str(path).endswith('.gz') else open
  with opener(path,'rt',encoding='utf-8') as f:
   data=json.load(f)
   for x in data: yield x
 for x in gen(): yield x
def select_code_repository(record):
 for r in record.get('repositories',[]) or []:
  u=r.get('url') if isinstance(r,dict) else r
  if u and 'github.com/' in u: return u
 for u in record.get('github_urls',[]) or []:
  if 'github.com/' in u: return u
 return None
def _paper_from_record(r,collected_at):
 title=r.get('title') or r.get('paper') or r.get('name'); url=r.get('url') or r.get('paper_url') or r.get('arxiv_url')
 if not title or not url: return None
 return ResearchPaper(title=title,abstract=r.get('abstract'),authors=r.get('authors') or [],paper_url=url,published_at=r.get('published_at') or r.get('date'),source=SourceProvenance(source_url=url,source_name='paperswithcode',collected_at=collected_at))
async def enrich_research_papers(papers,github_token=None):
 from src.github.metrics import enrich_paper_github
 return await enrich_paper_github(papers,github_token)
