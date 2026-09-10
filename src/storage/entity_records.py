from datetime import datetime,timezone
from sqlalchemy.dialects.postgresql import insert
from src.storage.models import EntityRecord
async def upsert_entity(session,record_type,source_name,source_url,payload,canonical_name=None,source_content_hash=None):
 now=datetime.now(timezone.utc)
 stmt=insert(EntityRecord).values(record_type=record_type,source_name=source_name,source_url=source_url,schema_version='1.0',canonical_name=canonical_name,payload=payload,source_content_hash=source_content_hash,collected_at=now,created_at=now).on_conflict_do_update(constraint='uq_entity_source',set_={'payload':payload,'canonical_name':canonical_name,'source_content_hash':source_content_hash,'collected_at':now})
 await session.execute(stmt)
