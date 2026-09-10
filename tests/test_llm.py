import asyncio
from src.llm.orchestrator import LLMOrchestrator
class P:
 def __init__(self,name): self.name=name; self.calls=0
 async def extract(self,prompt,schema): self.calls+=1; return {'ok':self.name}
def test_provider_order():
 async def run():
  p1=P('gemini'); p2=P('groq'); r=await LLMOrchestrator([p1,p2]).extract('hello',{'type':'object'}); assert r.provider=='gemini'
 asyncio.run(run())
