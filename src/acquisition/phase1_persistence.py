from src.storage.entity_records import upsert_entity
from src.storage.models import EntityMapping
from datetime import datetime,timezone
def sheet_rows(startups,products,papers,news=None,jobs=None):
 return {'Startups':[r.model_dump(mode='json')|{'source_url':str(r.source.source_url),'source_name':r.source.source_name} for r in startups],'Products':[r.model_dump(mode='json')|{'source_url':str(r.source.source_url),'source_name':r.source.source_name} for r in products],'Research Papers':[r.model_dump(mode='json')|{'paper_url':str(r.paper_url),'source_url':str(r.source.source_url)} for r in papers],'Jobs':[r.model_dump(mode='json') for r in (jobs or [])],'News':[r.model_dump(mode='json') for r in (news or [])],'Entity Mapping Log':[]}
async def persist_phase1(session,*,startups,products,papers,resolver):
 counts={'startups':0,'products':0,'papers':0}
 for typ,records in [('startup',startups),('product',products),('research_paper',papers)]:
  for r in records:
   name=getattr(r,'name',getattr(r,'title','')); res=resolver.resolve(name)
   await upsert_entity(session,typ,r.source.source_name,str(r.source.source_url),r.model_dump(mode='json'),res.canonical_name)
   if res.method!='unresolved': session.add(EntityMapping(raw_name=res.raw_name,normalized_name=res.normalized_name,canonical_name=res.canonical_name,entity_type=typ,match_method=res.method,confidence=res.confidence,created_at=datetime.now(timezone.utc)))
   counts[{'startup':'startups','product':'products','research_paper':'papers'}[typ]]+=1
 await session.commit(); return counts
