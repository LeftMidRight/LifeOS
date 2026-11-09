from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, JSON, DECIMAL, Index, Integer, String, text
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(MEDIUMTEXT(), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(10), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("(JSON_ARRAY())")
    )
    meta: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("(JSON_OBJECT())")
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3), nullable=True)


class AiInsight(Base):
    __tablename__ = "ai_insights"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)


Index("idx_entries_occurred", Entry.occurred_at.desc())
Index("idx_entries_kind", Entry.kind, Entry.occurred_at.desc())
Index("idx_entries_status", Entry.status, Entry.due_at)
Index("idx_insights_period", AiInsight.scope, AiInsight.period_start.desc())
