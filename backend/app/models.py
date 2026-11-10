from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, JSON, DECIMAL, ForeignKey, Index, Integer, String, UniqueConstraint, text
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


class ReviewChatSession(Base):
    __tablename__ = "review_chat_sessions"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)
    latest_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    __table_args__ = (UniqueConstraint("scope", "period_start", name="uq_review_chat_period"),)


class ReviewChatMessage(Base):
    __tablename__ = "review_chat_messages"

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        CHAR(36),
        ForeignKey("review_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(MEDIUMTEXT(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), nullable=False)

    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_review_chat_message_seq"),
    )


Index("idx_entries_occurred", Entry.occurred_at.desc())
Index("idx_entries_kind", Entry.kind, Entry.occurred_at.desc())
Index("idx_entries_status", Entry.status, Entry.due_at)
Index("idx_insights_period", AiInsight.scope, AiInsight.period_start.desc())
Index(
    "idx_review_chat_sessions_recent",
    ReviewChatSession.updated_at.desc(),
    ReviewChatSession.id.desc(),
)
