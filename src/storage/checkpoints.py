from datetime import datetime,timezone
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.storage.models import AcquisitionCheckpoint
async def get_checkpoint(session,source_name,query_key): return await session.scalar(select(AcquisitionCheckpoint).where(AcquisitionCheckpoint.source_name==source_name,AcquisitionCheckpoint.query_key==query_key))
async def save_checkpoint(session,*,source_name,query_key,next_offset,records_fetched,records_inserted,completed):
 stmt=insert(AcquisitionCheckpoint).values(source_name=source_name,query_key=query_key,next_offset=next_offset,records_fetched=records_fetched,records_inserted=records_inserted,completed=completed,updated_at=datetime.now(timezone.utc)).on_conflict_do_update(constraint='uq_acquisition_checkpoint',set_={'next_offset':next_offset,'records_fetched':records_fetched,'records_inserted':records_inserted,'completed':completed,'updated_at':datetime.now(timezone.utc)}).returning(AcquisitionCheckpoint.id)
 return await session.get(AcquisitionCheckpoint,(await session.execute(stmt)).scalar_one())
