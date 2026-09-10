from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import get_settings
s=get_settings(); engine=create_async_engine(s.database_url,pool_pre_ping=True,pool_size=10,max_overflow=20); AsyncSessionLocal=async_sessionmaker(engine,class_=AsyncSession,expire_on_commit=False)
async def get_session()->AsyncGenerator[AsyncSession,None]:
 async with AsyncSessionLocal() as session: yield session
async def close_database(): await engine.dispose()
