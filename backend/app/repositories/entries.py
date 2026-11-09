from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import to_utc_naive, utcnow
from app.models import Entry
from app.schemas import EntryCreate, EntryPatch, ListQuery

DATETIME_FIELDS = {"occurred_at", "due_at"}


async def create_entry(session: AsyncSession, data: EntryCreate) -> Entry:
    now = utcnow()
    entry = Entry(
        id=str(uuid4()),
        kind=data.kind,
        content=data.content,
        title=data.title,
        occurred_at=to_utc_naive(data.occurred_at) if data.occurred_at else to_utc_naive(now),
        created_at=to_utc_naive(now),
        updated_at=to_utc_naive(now),
        amount=data.amount,
        currency=data.currency,
        category=data.category,
        status=data.status or ("open" if data.kind == "todo" else None),
        due_at=to_utc_naive(data.due_at) if data.due_at else None,
        mood=data.mood,
        energy=data.energy,
        tags=data.tags,
        meta=data.meta,
        source=data.source,
        deleted_at=None,
    )
    session.add(entry)
    await session.flush()
    return entry


async def get_entry(session: AsyncSession, entry_id: str) -> Entry | None:
    result = await session.execute(
        select(Entry).where(Entry.id == entry_id, Entry.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def update_entry(session: AsyncSession, entry_id: str, patch: EntryPatch) -> Entry | None:
    entry = await get_entry(session, entry_id)
    if entry is None:
        return None

    for field_name in patch.model_fields_set:
        value = getattr(patch, field_name)
        if field_name in DATETIME_FIELDS and value is not None:
            value = to_utc_naive(value)
        setattr(entry, field_name, value)

    entry.updated_at = to_utc_naive(utcnow())
    await session.flush()
    return entry


async def delete_entry(session: AsyncSession, entry_id: str) -> bool:
    entry = await get_entry(session, entry_id)
    if entry is None:
        return False
    now = to_utc_naive(utcnow())
    entry.deleted_at = now
    entry.updated_at = now
    await session.flush()
    return True


async def list_entries(session: AsyncSession, query: ListQuery) -> list[Entry]:
    stmt = select(Entry).where(Entry.deleted_at.is_(None))
    if query.from_ is not None:
        stmt = stmt.where(Entry.occurred_at >= to_utc_naive(query.from_))
    if query.to is not None:
        stmt = stmt.where(Entry.occurred_at < to_utc_naive(query.to))
    if query.kind is not None:
        stmt = stmt.where(Entry.kind == query.kind)
    if query.status is not None:
        stmt = stmt.where(Entry.status == query.status)
    if query.q:
        stmt = stmt.where(Entry.content.like(f"%{query.q}%"))
    if query.tag:
        stmt = stmt.where(func.json_contains(Entry.tags, json.dumps(query.tag, ensure_ascii=False)))
    stmt = stmt.order_by(Entry.occurred_at.desc()).limit(query.limit).offset(query.offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def entries_in_range(session: AsyncSession, from_: datetime, to: datetime) -> list[Entry]:
    result = await session.execute(
        select(Entry)
        .where(
            Entry.deleted_at.is_(None),
            Entry.occurred_at >= to_utc_naive(from_),
            Entry.occurred_at < to_utc_naive(to),
        )
        .order_by(Entry.occurred_at.desc())
    )
    return list(result.scalars().all())
