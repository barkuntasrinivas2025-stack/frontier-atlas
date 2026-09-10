import hashlib
from datetime import datetime,timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.storage.models import RawDocument
from src.freshness.dedup import canonical_url
def content_hash(content): return hashlib.sha256(content.encode()).hexdigest()
async def save_raw_document(session:AsyncSession,*,url,source_name,raw_html=None,extracted_text=None,content_type=None,http_status=None,metadata=None):
 u=canonical_url(url); body=extracted_text or raw_html or ''; digest=content_hash(body) if body else None; now=datetime.now(timezone.utc)
 stmt=insert(RawDocument).values(url=u,source_name=source_name,raw_html=raw_html,extracted_text=extracted_text,content_type=content_type,http_status=http_status,content_hash=digest,discovered_at=now,collected_at=now,metadata_json=metadata).on_conflict_do_nothing(index_elements=[RawDocument.url]).returning(RawDocument.id)
 rid=(await session.execute(stmt)).scalar_one_or_none()
 if rid: return await session.get(RawDocument,rid),True
 return await session.scalar(select(RawDocument).where(RawDocument.url==u)),False
