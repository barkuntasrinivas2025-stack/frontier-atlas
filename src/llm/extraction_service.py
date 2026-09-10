from src.llm.orchestrator import LLMOrchestrator
class ExtractionService:
 def __init__(self,orchestrator): self.orchestrator=orchestrator
 async def extract(self,text,schema): return await self.orchestrator.extract(text,schema)
