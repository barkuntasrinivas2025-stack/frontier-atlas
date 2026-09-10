import asyncio,json,sys
from src.crawlers.arxiv_ingestion import ArxivIngestionService
from src.storage.database import AsyncSessionLocal
from src.config.settings import get_settings
async def main():
 s=get_settings()
 async with AsyncSessionLocal() as session: print(json.dumps(await ArxivIngestionService(session,100,s.http_timeout_seconds,10).ingest(max_records=1000),indent=2))
if __name__=='__main__': asyncio.run(main(),loop_factory=__import__('asyncio').SelectorEventLoop) if sys.platform=='win32' else asyncio.run(main())
