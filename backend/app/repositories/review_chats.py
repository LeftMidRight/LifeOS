from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import to_utc_naive, utcnow
from app.models import ReviewChatMessage, ReviewChatSession

Cursor = tuple[datetime, str]


async def find_chat_by_period(
    session: AsyncSession, scope: str, period_start: datetime
) -> ReviewChatSession | None:
    result = await session.execute(
        select(ReviewChatSession)
        .where(
            ReviewChatSession.scope == scope,
            ReviewChatSession.period_start == to_utc_naive(period_start),
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_chat(session: AsyncSession, session_id: str) -> ReviewChatSession | None:
    result = await session.execute(
        select(ReviewChatSession)
        .where(ReviewChatSession.id == session_id)
        # 让同一 session 里缓存的实例拿到最新 latest_sequence，避免乐观并发读到旧值。
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def list_chats(
    session: AsyncSession,
    scope: str,
    limit: int,
    cursor_values: Cursor | None = None,
) -> list[ReviewChatSession]:
    # 只展示至少有一轮成功问答的会话；失败请求不会写入消息，因此无需额外配对过滤。
    stmt = (
        select(ReviewChatSession)
        .where(
            exists().where(
                ReviewChatMessage.session_id == ReviewChatSession.id,
                ReviewChatMessage.role == "assistant",
            )
        )
        .order_by(ReviewChatSession.updated_at.desc(), ReviewChatSession.id.desc())
        .limit(limit)
        # cursor 必须基于 DB 的 DATETIME(3) 精度，避免内存对象的微秒造成分页重复。
        .execution_options(populate_existing=True)
    )
    if scope != "all":
        stmt = stmt.where(ReviewChatSession.scope == scope)
    if cursor_values is not None:
        cursor_updated_at, cursor_id = cursor_values
        stmt = stmt.where(
            or_(
                ReviewChatSession.updated_at < cursor_updated_at,
                (
                    (ReviewChatSession.updated_at == cursor_updated_at)
                    & (ReviewChatSession.id < cursor_id)
                ),
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_messages(
    session: AsyncSession,
    session_id: str,
    *,
    before_sequence: int | None = None,
    limit: int = 100,
) -> tuple[list[ReviewChatMessage], bool]:
    """返回按 sequence 升序的消息页，以及是否还有更早的一页。"""
    stmt = select(ReviewChatMessage).where(ReviewChatMessage.session_id == session_id)
    if before_sequence is not None:
        stmt = stmt.where(ReviewChatMessage.sequence < before_sequence)
    stmt = stmt.order_by(ReviewChatMessage.sequence.desc()).limit(limit + 1)
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    return list(reversed(rows[:limit])), has_more


async def recent_messages(
    session: AsyncSession, session_id: str, limit: int = 20
) -> list[ReviewChatMessage]:
    """最近 N 条消息，按从旧到新的顺序返回，供模型上下文使用。"""
    result = await session.execute(
        select(ReviewChatMessage)
        .where(ReviewChatMessage.session_id == session_id)
        .order_by(ReviewChatMessage.sequence.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def append_messages_if_current(
    session: AsyncSession,
    session_id: str,
    expected_sequence: int,
    user_text: str,
    assistant_text: str,
    *,
    period_end: datetime | None = None,
) -> bool:
    """只有会话仍停在 expected_sequence 时才原子追加一问一答。

    period_end 仅在继续当前周期会话时传入，用于跟随当前周/日的最新范围；
    历史会话保持创建时保存的边界。调用方负责 commit/rollback。
    """
    now = to_utc_naive(utcnow())
    values: dict[str, object] = {
        "latest_sequence": expected_sequence + 2,
        "updated_at": now,
    }
    if period_end is not None:
        values["period_end"] = to_utc_naive(period_end)
    result = await session.execute(
        update(ReviewChatSession)
        .where(
            ReviewChatSession.id == session_id,
            ReviewChatSession.latest_sequence == expected_sequence,
        )
        .values(**values)
        # 不需要同步 ORM 身份映射；否则会把调用方持有的 session 对象标记为过期，
        # 之后在异步上下文里访问属性会触发 MissingGreenlet。
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return False

    session.add_all(
        [
            ReviewChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                sequence=expected_sequence + 1,
                role="user",
                content=user_text,
                created_at=now,
            ),
            ReviewChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                sequence=expected_sequence + 2,
                role="assistant",
                content=assistant_text,
                created_at=now,
            ),
        ]
    )
    await session.flush()
    return True


async def create_chat_with_messages(
    session: AsyncSession,
    *,
    scope: str,
    period_start: datetime,
    period_end: datetime,
    user_text: str,
    assistant_text: str,
) -> ReviewChatSession:
    now = to_utc_naive(utcnow())
    chat = ReviewChatSession(
        id=str(uuid4()),
        scope=scope,
        period_start=to_utc_naive(period_start),
        period_end=to_utc_naive(period_end),
        created_at=now,
        updated_at=now,
        latest_sequence=2,
    )
    session.add(chat)
    await session.flush()
    session.add_all(
        [
            ReviewChatMessage(
                id=str(uuid4()),
                session_id=chat.id,
                sequence=1,
                role="user",
                content=user_text,
                created_at=now,
            ),
            ReviewChatMessage(
                id=str(uuid4()),
                session_id=chat.id,
                sequence=2,
                role="assistant",
                content=assistant_text,
                created_at=now,
            ),
        ]
    )
    await session.flush()
    return chat


async def delete_chat(session: AsyncSession, session_id: str) -> bool:
    result = await session.execute(
        delete(ReviewChatSession).where(ReviewChatSession.id == session_id)
    )
    return result.rowcount == 1
