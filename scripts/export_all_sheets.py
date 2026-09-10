import asyncio
from sqlalchemy import select
from src.storage.database import AsyncSessionLocal
from src.storage.models import EntityRecord,EntityMapping
from src.storage.sheets import GoogleSheetsExporter,TABS

def rows(records,typ):
 out=[]
 for r in records:
  p=dict(r.payload); p['source_url']=r.source_url; p['source_name']=r.source_name; out.append(p)
 return out
async def main():
 async with AsyncSessionLocal() as s:
  allr=(await s.scalars(select(EntityRecord).order_by(EntityRecord.id))).all(); maps=(await s.scalars(select(EntityMapping).order_by(EntityMapping.id))).all()
 exp=GoogleSheetsExporter(); exp.ensure_tabs(); groups={'Startups':'startup','Products':'product','Research Papers':'research_paper','Jobs':'job','News':'news'}
 for tab,typ in groups.items(): exp.replace_rows(tab,rows([r for r in allr if r.record_type==typ],typ))
 exp.replace_rows('Entity Mapping Log',[{'raw_name':m.raw_name,'normalized_name':m.normalized_name,'canonical_name':m.canonical_name,'entity_type':m.entity_type,'match_method':m.match_method,'confidence':m.confidence,'created_at':m.created_at.isoformat()} for m in maps])
 print({t:sum(r.record_type==k for r in allr) for t,k in groups.items()})
if __name__=='__main__': asyncio.run(main())
