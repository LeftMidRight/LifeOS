from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)

from app.core.time import to_iso_z

Kind = Literal["journal", "thought", "expense", "todo", "habit", "metric"]
TodoStatus = Literal["open", "done", "dropped"]
Source = Literal["manual", "capture", "import", "api"]


def to_camel(value: str) -> str:
    head, *rest = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        protected_namespaces=(),
    )


Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Title = Annotated[str, StringConstraints(max_length=200)]


class EntryCreate(CamelModel):
    kind: Kind
    content: Content
    occurred_at: AwareDatetime | None = None
    title: Title | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    category: str | None = Field(default=None, max_length=20)
    status: TodoStatus | None = None
    due_at: AwareDatetime | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    meta: dict[str, Any] = Field(default_factory=dict)
    source: Source = "manual"


class EntryPatch(CamelModel):
    kind: Kind | None = None
    content: Content | None = None
    occurred_at: AwareDatetime | None = None
    title: Title | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    category: str | None = Field(default=None, max_length=20)
    status: TodoStatus | None = None
    due_at: AwareDatetime | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=5)
    tags: list[Tag] | None = Field(default=None, max_length=20)
    meta: dict[str, Any] | None = None

    @model_validator(mode="after")
    def reject_null_for_non_nullable_fields(self) -> EntryPatch:
        non_nullable = {"kind", "content", "occurred_at", "currency", "tags", "meta"}
        for field_name in non_nullable:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} 不能为 null")
        return self


class EntryRead(CamelModel):
    id: str
    kind: Kind
    content: str
    title: str | None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime
    amount: float | None
    currency: str
    category: str | None
    status: TodoStatus | None
    due_at: datetime | None
    mood: int | None
    energy: int | None
    tags: list[str]
    meta: dict[str, Any]
    source: Source

    @field_serializer("occurred_at", "created_at", "updated_at", "due_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return to_iso_z(value) if value is not None else None


class EntryListResponse(CamelModel):
    items: list[EntryRead]
    count: int


class ListQuery(BaseModel):
    from_: AwareDatetime | None = None
    to: AwareDatetime | None = None
    kind: Kind | None = None
    status: TodoStatus | None = None
    q: str | None = None
    tag: str | None = None
    limit: int = 500
    offset: int = 0


class CategoryTotal(CamelModel):
    category: str
    total: float
    count: int


class Stats(CamelModel):
    from_: datetime = Field(alias="from")
    to: datetime
    total_spent: float
    by_category: list[CategoryTotal]
    by_kind: dict[str, int]
    open_todos: int
    done_todos: int
    avg_mood: float | None
    entry_count: int

    @field_serializer("from_", "to")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso_z(value)


class Insight(CamelModel):
    scope: Literal["daily", "weekly"]
    from_: datetime = Field(alias="from")
    to: datetime
    headline: str
    summary: str
    themes: list[str]
    spending: str
    todos: str
    mood: Literal["up", "flat", "down", "unknown"]
    suggestion: str
    model: str
    generated_at: datetime

    @field_serializer("from_", "to", "generated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso_z(value)


class CaptureRequest(CamelModel):
    text: Content
    at: AwareDatetime | None = None


class CaptureParsed(CamelModel):
    kind: Kind
    content: str
    tags: list[str]
    amount: float | None
    category: str | None
    due_at: datetime | None
    status: Literal["open"] | None
    confidence: float
    note: str

    @field_serializer("due_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return to_iso_z(value) if value is not None else None


class CaptureResponse(CamelModel):
    entry: EntryRead
    parsed: CaptureParsed


class InsightResponse(CamelModel):
    insight: Insight
    warning: str | None
    stats: Stats


class InsightPreviewResponse(CamelModel):
    scope: Literal["daily", "weekly"]
    from_: datetime = Field(alias="from")
    to: datetime
    stats: Stats
    payload: dict[str, Any]
    payload_text: str
    insight: Insight | None
    entry_count: int

    @field_serializer("from_", "to")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso_z(value)


ChatMessageText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4_000)
]
ChatScope = Literal["daily", "weekly"]
ChatRole = Literal["user", "assistant"]


class ChatMessageCreate(CamelModel):
    scope: ChatScope | None = None
    session_id: str | None = None
    message: ChatMessageText

    @model_validator(mode="after")
    def require_scope_or_session(self) -> ChatMessageCreate:
        if self.scope is None and not self.session_id:
            raise ValueError("必须提供 scope 或 sessionId")
        return self


class ChatMessageRead(CamelModel):
    id: str
    session_id: str
    sequence: int
    role: ChatRole
    content: str
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso_z(value)


class ChatSessionSummary(CamelModel):
    id: str
    scope: ChatScope
    period_start: datetime
    period_end: datetime
    message_count: int
    updated_at: datetime

    @field_serializer("period_start", "period_end", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return to_iso_z(value)


class ChatSessionRead(ChatSessionSummary):
    created_at: datetime
    latest_sequence: int

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return to_iso_z(value)


class ChatSessionListResponse(CamelModel):
    items: list[ChatSessionSummary]
    next_cursor: str | None


class ChatViewResponse(CamelModel):
    session: ChatSessionRead | None
    messages: list[ChatMessageRead]
    has_more: bool
    before_sequence: int | None
    insight: Insight | None
    stats: Stats


class ChatSendResponse(CamelModel):
    session: ChatSessionRead
    messages: list[ChatMessageRead]
