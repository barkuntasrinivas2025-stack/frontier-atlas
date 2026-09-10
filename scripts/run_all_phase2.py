import asyncio,json,sys
from datetime import datetime,timezone
from src.acquisition.phase2 import collect_phase2
from src.storage.database import AsyncSessionLocal
from src.storage.entity_records import upsert_entity
from src.storage.models import EntityMapping
from src.resolution.resolver import EntityResolver
from src.resolution.seed import DEFAULT_SEED
async def main():
 news,jobs,stats=await collect_phase2(); resolver=EntityResolver(DEFAULT_SEED)
 async with AsyncSessionLocal() as session:
  for r in news:
   x=resolver.resolve(r.title)
   await upsert_entity(session,'news',r.source.source_name,str(r.url),r.model_dump(mode='json'),x.canonical_name)
   if x.method != 'unresolved':
    session.add(EntityMapping(
     raw_name=x.raw_name,
     normalized_name=x.normalized_name,
     canonical_name=x.canonical_name,
     entity_type='news',
     match_method=x.method,
     confidence=x.confidence,
     created_at=datetime.now(timezone.utc)
    ))
  for r in jobs:
   x=resolver.resolve(r.company or r.title)
   await upsert_entity(session,'job',r.source.source_name,str(r.url),r.model_dump(mode='json'),x.canonical_name)
   if x.method != 'unresolved':
    session.add(EntityMapping(
     raw_name=x.raw_name,
     normalized_name=x.normalized_name,
     canonical_name=x.canonical_name,
     entity_type='job',
     match_method=x.method,
     confidence=x.confidence,
     created_at=datetime.now(timezone.utc)
    ))
  await session.commit()
 print(json.dumps({'news':len(news),'jobs':len(jobs),'stats':stats.__dict__},default=str,indent=2))
if __name__=='__main__': asyncio.run(main(),loop_factory=__import__('asyncio').SelectorEventLoop) if sys.platform=='win32' else asyncio.run(main())
