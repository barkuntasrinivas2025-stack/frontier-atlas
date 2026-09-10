from dataclasses import dataclass,asdict
from src.crawlers.arxiv import ArxivCrawler
from src.storage.checkpoints import get_checkpoint,save_checkpoint
from src.storage.raw_documents import save_raw_document
from src.utils.http import HTTPClient
@dataclass
class IngestionStats: fetched:int=0; inserted:int=0; skipped:int=0; pages:int=0; start_offset:int=0; next_offset:int=0; completed:bool=False
class ArxivIngestionService:
 def __init__(self,session,batch_size=100,http_timeout=30,concurrency=10): self.session=session; self.batch_size=batch_size; self.http_timeout=http_timeout; self.concurrency=concurrency
 async def ingest(self,query='cat:cs.AI',max_records=1000,start=None,resume=True):
  if max_records<=0:return asdict(IngestionStats(completed=True))
  cp=await get_checkpoint(self.session,'arxiv',query) if resume else None
  offset=start if start is not None else (cp.next_offset if cp else 0); st=IngestionStats(start_offset=offset,next_offset=offset)
  if cp and cp.completed and start is None: st.completed=True; return asdict(st)
  async with HTTPClient(self.http_timeout,concurrency=self.concurrency) as http:
   crawler=ArxivCrawler(http); remaining=max_records
   while remaining:
    size=min(self.batch_size,remaining); papers=await crawler.search(query,offset,size); st.pages+=1
    if not papers: st.completed=True; break
    for p in papers:
     _,inserted=await save_raw_document(self.session,url=p.source_url,source_name='arxiv',extracted_text=p.title+'\n'+p.abstract,metadata={'arxiv_id':p.arxiv_id})
     st.fetched+=1; st.inserted+=int(inserted); st.skipped+=int(not inserted)
    offset+=len(papers); remaining-=len(papers); st.next_offset=offset
    done=len(papers)<size or remaining==0
    await save_checkpoint(self.session,source_name='arxiv',query_key=query,next_offset=offset,records_fetched=st.fetched,records_inserted=st.inserted,completed=done); await self.session.commit()
    if len(papers)<size: st.completed=True; break
  return asdict(st)
