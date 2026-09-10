import asyncio,sys
from src.storage.database import engine
from src.storage.models import Base
async def init_db():
 async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
if __name__=='__main__': asyncio.run(init_db(),loop_factory=asyncio.SelectorEventLoop) if sys.platform=='win32' else asyncio.run(init_db())
