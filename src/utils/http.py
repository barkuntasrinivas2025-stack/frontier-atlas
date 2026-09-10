import asyncio, random, aiohttp
RETRYABLE={408,425,429,500,502,503,504}
class HTTPClient:
    def __init__(self,timeout_seconds=30,max_retries=5,concurrency=20): self.timeout=aiohttp.ClientTimeout(total=timeout_seconds); self.max_retries=max_retries; self.sem=asyncio.Semaphore(concurrency); self.session=None
    async def __aenter__(self):
        self.session=aiohttp.ClientSession(timeout=self.timeout,headers={'User-Agent':'FrontierAtlas/1.0 (+https://github.com/barkuntasrinivas2025-stack/frontier-atlas)'}) ; return self
    async def __aexit__(self,*args): await self.session.close()
    async def get(self,url,**kwargs):
        async with self.sem:
            for attempt in range(self.max_retries+1):
                try:
                    async with self.session.get(url,**kwargs) as r:
                        body=await r.text(errors='replace')
                        if r.status not in RETRYABLE or attempt==self.max_retries: return r.status,body,dict(r.headers)
                        ra=r.headers.get('Retry-After'); delay=float(ra) if ra and ra.isdigit() else min(30,2**attempt)+random.random()/2
                except (aiohttp.ClientError,asyncio.TimeoutError):
                    if attempt==self.max_retries: raise
                    delay=min(30,2**attempt)+random.random()/2
                await asyncio.sleep(delay)
