import json, aiohttp
class GeminiProvider:
 name='gemini'
 def __init__(self,api_key,model='gemini-3.6-flash'): self.api_key=api_key; self.model=model
 async def extract(self,prompt,schema):
  if not self.api_key: raise RuntimeError('gemini: API key not configured')
  url=f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}'
  payload={'contents':[{'parts':[{'text':prompt+'\nJSON schema:\n'+json.dumps(schema)}]}], 'generationConfig':{'responseMimeType':'application/json'}}
  async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
   async with s.post(url,json=payload) as r:
    text=await r.text()
    if r.status>=400: raise RuntimeError(f'gemini HTTP {r.status}: {text[:300]}')
    d=json.loads(text); return json.loads(d['candidates'][0]['content']['parts'][0]['text'])
