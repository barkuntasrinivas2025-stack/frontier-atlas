import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
TRACKING = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content','gclid','fbclid','ref','ref_src'}
def canonical_url(url: str) -> str:
    p=urlsplit(url.strip()); scheme=p.scheme.lower(); netloc=p.netloc.lower()
    if netloc.endswith(':80') and scheme=='http': netloc=netloc[:-3]
    if netloc.endswith(':443') and scheme=='https': netloc=netloc[:-4]
    path=p.path.rstrip('/') or '/'
    q=sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in TRACKING)
    return urlunsplit((scheme,netloc,path,'&'.join(f'{k}={v}' for k,v in q),''))
def sha256_text(text: str) -> str: return hashlib.sha256(text.encode('utf-8')).hexdigest()
