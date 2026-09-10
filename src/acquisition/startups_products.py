import re
from datetime import datetime
from bs4 import BeautifulSoup
from src.extraction.schemas import Startup,Product,SourceProvenance
YC='https://www.ycombinator.com/companies/industry/ai'
PH='https://api.producthunt.com/v2/api/graphql'
def parse_yc_company_cards(html,collected_at):
 s=BeautifulSoup(html,'lxml'); out=[]; seen=set()
 for a in s.select('a[href*="/companies/"]'):
  href=a.get('href',''); name=a.get_text(' ',strip=True)
  if not name or href in seen: continue
  seen.add(href); url=href if href.startswith('http') else 'https://www.ycombinator.com'+href
  out.append(Startup(name=name,source=SourceProvenance(source_url=url,source_name='ycombinator_ai',collected_at=collected_at)))
 return out
async def crawl_yc_ai_startups(session,pages=20):
 out={}; collected=datetime.utcnow().astimezone()
 for page in range(1,pages+1):
  async with session.get(f'{YC}?page={page}') as r:
   if r.status!=200: continue
   for x in parse_yc_company_cards(await r.text(),collected): out[str(x.source.source_url)]=x
 return list(out.values())
def parse_product_hunt_response(payload,collected_at=None):
 collected_at=collected_at or datetime.utcnow().astimezone(); out=[]
 for e in payload.get('data',{}).get('posts',{}).get('edges',[]):
  n=e.get('node',{}); name=n.get('name'); url=n.get('url')
  if not name or not url: continue
  topics=n.get('topics',{}).get('edges',[]); category=topics[0].get('node',{}).get('name') if topics else None
  out.append(Product(name=name,description=n.get('description') or n.get('tagline'),website=n.get('website'),category=category,source=SourceProvenance(source_url=url,source_name='product_hunt',collected_at=collected_at)))
 return out
async def crawl_product_hunt(session,access_token,pages=10):
 q='query($after:String){posts(first:50,after:$after){edges{node{name tagline description url website topics(first:1){edges{node{name}}}}}pageInfo{hasNextPage endCursor}}}'
 out=[]; after=None
 for _ in range(pages):
  async with session.post(PH,json={'query':q,'variables':{'after':after}},headers={'Authorization':f'Bearer {access_token}'}) as r:
   if r.status!=200: break
   d=await r.json(); out.extend(parse_product_hunt_response(d)); pi=d.get('data',{}).get('posts',{}).get('pageInfo',{}); after=pi.get('endCursor')
   if not pi.get('hasNextPage'): break
 return out
