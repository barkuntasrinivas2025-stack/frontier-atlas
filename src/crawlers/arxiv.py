import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
@dataclass
class ArxivPaper:
 arxiv_id:str; title:str; abstract:str; authors:list[str]; published_at:datetime; updated_at:datetime|None; pdf_url:str; source_url:str; categories:list[str]; primary_category:str|None
class ArxivCrawler:
 def __init__(self,http): self.http=http
 async def search(self,query='cat:cs.AI',start=0,max_results=100,sort_by='submittedDate',sort_order='descending'):
  params={'search_query':query,'start':start,'max_results':max_results,'sortBy':sort_by,'sortOrder':sort_order}
  status,body,_=await self.http.get('https://export.arxiv.org/api/query',params=params)
  if status!=200: raise RuntimeError(f'Arxiv HTTP {status}')
  root=ET.fromstring(body); ns={'a':'http://www.w3.org/2005/Atom'}; out=[]
  for e in root.findall('a:entry',ns):
   def t(tag):
    x=e.find('a:'+tag,ns); return (x.text or '').strip() if x is not None else ''
   links=e.findall('a:link',ns); pdf=next((x.attrib.get('href') for x in links if x.attrib.get('title')=='pdf'),None); url=t('id')
   pub=datetime.fromisoformat(t('published').replace('Z','+00:00')); upd=t('updated'); authors=[x.find('a:name',ns).text for x in e.findall('a:author',ns)]
   cats=[x.attrib.get('term') for x in e.findall('a:category',ns)]; out.append(ArxivPaper(url.rsplit('/',1)[-1],t('title').replace('\n',' '),t('summary').replace('\n',' '),authors,pub,datetime.fromisoformat(upd.replace('Z','+00:00')) if upd else None,pdf,url,cats,cats[0] if cats else None))
  return out
