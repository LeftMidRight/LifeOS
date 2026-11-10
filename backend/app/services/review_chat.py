from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.time import (
    UTC,
    day_range,
    to_day_key,
    to_iso_z,
    to_utc_naive,
    utcnow,
    week_range,
)
from app.models import AiInsight, ReviewChatMessage, ReviewChatSession
from app.repositories.entries import entries_in_range
from app.repositories.review_chats import (
    append_messages_if_current,
    create_chat_with_messages,
    delete_chat,
    find_chat_by_period,
    get_chat,
    list_chats,
    list_messages,
    recent_messages,
)
from app.schemas import Insight, Stats
from app.services.insight import compact_entries
from app.services.stats import compute_stats

MessageLimit = int


class ChatNotConfigured(Exception):
    """聊天需要模型，但服务端没有配置 API Key。"""


class ChatNotFound(Exception):
    """指定的历史会话不存在。"""


class ChatConflict(Exception):
    """会话被其他请求更新，或当前周期的会话身份不匹配。"""


class ChatUpstreamError(Exception):
    """模型服务不可用或返回了无效答复。"""


@dataclass
class ChatView:
    session: ReviewChatSession | None
    messages: list[ReviewChatMessage]
    has_more: bool
    before_sequence: int | None
    insight: Insight | None
    stats: Stats


@dataclass
class ChatSessionPage:
    items: list[ReviewChatSession]
    next_cursor: str | None
    message_counts: dict[str, int]


@dataclass
class ChatSendResult:
    session: ReviewChatSession
    messages: list[ReviewChatMessage]


CHAT_SYSTEM_PROMPT = """你是 LifeOS 的回顾对话助手。用户会带着一个周期的记录、统计和已保存的回顾摘要来和你聊天。
你的任务是基于这些真实材料，回答用户关于这段时间的问题、帮他看清模式和给出具体建议。

硬性要求：
1. 只使用提供的事实，不要编造记录里没有的事；信息不足时直接说明。
2. 提到具体事情时引用记录里的原话片段，不要改写事实。
3. 语气像一个很了解他、但不奉承的老朋友：具体、克制、不说教。
4. 用中文回答，直接输出正文，不要 markdown 代码块，也不要输出 JSON。
5. 不要声称你能看到这个周期之外的数据。"""


def _current_range(scope: str) -> tuple[datetime, datetime]:
    if scope == "weekly":
        return week_range()
    return day_range(to_day_key(utcnow()))


def _encode_cursor(chat: ReviewChatSession) -> str:
    return f"{chat.updated_at.isoformat()}|{chat.id}"


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        timestamp, chat_id = cursor.split("|", 1)
        return datetime.fromisoformat(timestamp), chat_id
    except (ValueError, TypeError) as error:
        raise ValueError("cursor 不合法") from error


async def _insight_for(
    session: AsyncSession, scope: str, start: datetime, end: datetime
) -> Insight | None:
    row = await session.scalar(
        select(AiInsight)
        .where(
            AiInsight.scope == scope,
            AiInsight.period_start == to_utc_naive(start),
            AiInsight.period_end == to_utc_naive(end),
        )
        .order_by(AiInsight.created_at.desc())
        .limit(1)
    )
    return Insight.model_validate(row.payload) if row is not None else None


async def _period_data(
    session: AsyncSession,
    scope: str,
    start: datetime,
    end: datetime,
) -> tuple[Stats, Insight | None, list[dict[str, object]]]:
    entries = await entries_in_range(session, start, end)
    stats = compute_stats(entries, start, end)
    insight = await _insight_for(session, scope, start, end)
    return stats, insight, compact_entries(entries)


async def get_current_chat(session: AsyncSession, scope: str) -> ChatView:
    start, end = _current_range(scope)
    chat = await find_chat_by_period(session, scope, start)
    stats, insight, _ = await _period_data(session, scope, start, end)

    if chat is None:
        return ChatView(
            session=None,
            messages=[],
            has_more=False,
            before_sequence=None,
            insight=insight,
            stats=stats,
        )

    messages, has_more = await list_messages(session, chat.id, limit=100)
    return ChatView(
        session=chat,
        messages=messages,
        has_more=has_more,
        before_sequence=messages[0].sequence if has_more and messages else None,
        insight=insight,
        stats=stats,
    )


async def get_chat_session(
    session: AsyncSession,
    session_id: str,
    before_sequence: int | None,
    limit: int,
) -> ChatView:
    chat = await get_chat(session, session_id)
    if chat is None:
        raise ChatNotFound("会话不存在")

    # 历史会话使用自己保存的周期边界，不受当前日期影响；DB 里是 UTC naive。
    start = chat.period_start.replace(tzinfo=UTC)
    end = chat.period_end.replace(tzinfo=UTC)
    stats, insight, _ = await _period_data(session, chat.scope, start, end)
    messages, has_more = await list_messages(
        session, chat.id, before_sequence=before_sequence, limit=limit
    )
    return ChatView(
        session=chat,
        messages=messages,
        has_more=has_more,
        before_sequence=messages[0].sequence if has_more and messages else None,
        insight=insight,
        stats=stats,
    )


async def list_chat_sessions(
    session: AsyncSession, scope: str, limit: int, cursor: str | None
) -> ChatSessionPage:
    limit = max(1, min(limit, 100))
    cursor_values = _decode_cursor(cursor) if cursor else None
    rows = await list_chats(session, scope, limit + 1, cursor_values)
    has_more = len(rows) > limit
    items = rows[:limit]
    message_counts: dict[str, int] = {}
    if items:
        counts = await session.execute(
            select(ReviewChatMessage.session_id, func.count())
            .where(ReviewChatMessage.session_id.in_([item.id for item in items]))
            .group_by(ReviewChatMessage.session_id)
        )
        message_counts = {session_id: count for session_id, count in counts.all()}
    return ChatSessionPage(
        items=items,
        next_cursor=_encode_cursor(items[-1]) if has_more and items else None,
        message_counts=message_counts,
    )


async def _call_chat_model(
    context: dict[str, object],
    history: list[dict[str, str]],
    message: str,
    settings: Settings,
) -> str:
    system = f"{CHAT_SYSTEM_PROMPT}\n\n当前周期的记录上下文：\n{json.dumps(context, ensure_ascii=False)}"
    body = {
        "model": settings.lifeos_llm_model,
        "temperature": 0.6,
        "messages": [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": message},
        ],
    }
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {settings.lifeos_llm_api_key}",
        "x-opencode-session": settings.lifeos_llm_session_id,
    }
    url = f"{settings.lifeos_llm_base_url.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as error:  # noqa: BLE001 - 统一转成安全的用户错误
        raise ChatUpstreamError("模型服务暂时不可用，请稍后重试") from error

    if not isinstance(content, str) or not content.strip():
        raise ChatUpstreamError("模型返回为空，请重试")
    return content.strip()


async def send_chat_message(
    session: AsyncSession,
    message: str,
    *,
    scope: str | None = None,
    session_id: str | None = None,
    settings: Settings | None = None,
) -> ChatSendResult:
    settings = settings or get_settings()
    if not settings.lifeos_llm_api_key:
        raise ChatNotConfigured("未配置 LIFEOS_LLM_API_KEY，无法进行对话")

    chat = await get_chat(session, session_id) if session_id else None
    if session_id and chat is None:
        raise ChatNotFound("会话不存在")

    if chat is not None:
        # 带 scope 表示从前端当前视图续聊：会话必须仍是当前周期的那个。
        if scope is not None:
            start, _ = _current_range(scope)
            if chat.scope != scope or chat.period_start != to_utc_naive(start):
                raise ChatConflict("会话与当前回顾周期不一致，请刷新后重试")
        target_scope = chat.scope
        period_start = chat.period_start.replace(tzinfo=UTC)
        period_end = chat.period_end.replace(tzinfo=UTC)
        chat_id: str | None = chat.id
        expected_sequence = chat.latest_sequence
        history_rows = await recent_messages(session, chat.id, limit=20)
    else:
        if scope is None:
            raise ValueError("当前周期对话必须提供 scope")
        target_scope = scope
        period_start, period_end = _current_range(scope)
        existing = await find_chat_by_period(session, scope, period_start)
        chat_id = existing.id if existing is not None else None
        expected_sequence = existing.latest_sequence if existing is not None else 0
        history_rows = (
            await recent_messages(session, existing.id, limit=20)
            if existing is not None
            else []
        )

    stats, insight, entries = await _period_data(
        session, target_scope, period_start, period_end
    )
    context: dict[str, object] = {
        "scope": target_scope,
        "from": to_iso_z(period_start),
        "to": to_iso_z(period_end),
        "stats": stats.model_dump(mode="json", by_alias=True),
        "insight": insight.model_dump(mode="json", by_alias=True) if insight else None,
        "entries": entries,
    }
    history = [{"role": row.role, "content": row.content} for row in history_rows]

    # 外部模型调用期间不持有数据库事务；这里结束只读事务，释放连接。
    await session.rollback()

    reply = await _call_chat_model(context, history, message, settings)

    if chat_id is not None:
        appended = await append_messages_if_current(
            session,
            chat_id,
            expected_sequence,
            message,
            reply,
            # scope 存在表示这是「当前周期」请求，需要推进周期边界；
            # 只带 sessionId 的历史续聊沿用其保存的边界。
            period_end=period_end if scope is not None else None,
        )
        if not appended:
            await session.rollback()
            raise ChatConflict("会话已被其他请求更新，请刷新后重试")
        updated = await get_chat(session, chat_id)
        result_messages, _ = await list_messages(session, chat_id, limit=2)
    else:
        try:
            updated = await create_chat_with_messages(
                session,
                scope=target_scope,
                period_start=period_start,
                period_end=period_end,
                user_text=message,
                assistant_text=reply,
            )
        except IntegrityError as error:
            await session.rollback()
            raise ChatConflict("该周期的会话刚被其他请求创建，请重试") from error
        result_messages, _ = await list_messages(session, updated.id, limit=2)

    if updated is None:
        await session.rollback()
        raise ChatNotFound("会话不存在")
    await session.commit()
    return ChatSendResult(session=updated, messages=result_messages)


async def delete_chat_session(session: AsyncSession, session_id: str) -> bool:
    return await delete_chat(session, session_id)
