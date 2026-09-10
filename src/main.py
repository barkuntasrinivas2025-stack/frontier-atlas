import asyncio,sys,logging
from src.storage.init_db import init_db
async def main():
 logging.basicConfig(level=logging.INFO); await init_db(); logging.info('Frontier Atlas pipeline ready')
def run():
 asyncio.run(main(),loop_factory=asyncio.SelectorEventLoop) if sys.platform=='win32' else asyncio.run(main())
if __name__=='__main__': run()
