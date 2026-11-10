import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.time import day_range, to_day_key, to_utc_naive, utcnow, week_range
from app.models import AiInsight, ReviewChatMessage, ReviewChatSession
from app.repositories.entries import create_entry
from app.repositories.review_chats import (
    append_messages_if_current,
    create_chat_with_messages,
    get_chat,
)
from app.schemas import EntryCreate
from app.services.review_chat import (
    ChatConflict,
    ChatNotConfigured,
    ChatNotFound,
    ChatUpstreamError,
    get_chat_session,
    get_current_chat,
    list_chat_sessions,
    send_chat_message,
)

UTC = timezone.utc
URL = "https://api.deepseek.com/v1/chat/completions"


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("LIFEOS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LIFEOS_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LIFEOS_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("LIFEOS_LLM_SESSION_ID", "lifeos-test")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def request_json(route) -> dict:
    return json.loads(route.calls[0].request.content.decode())


def mock_reply(route, text: str = "这是模型的回答。"):
    return route.mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": text}}]}
        )
    )


async def seed_entry(session: AsyncSession, content: str, at: datetime) -> None:
    await create_entry(
        session,
        EntryCreate(kind="journal", content=content, occurred_at=at),
    )
    await session.commit()


def today_at(hour: int = 12) -> datetime:
    start, _ = day_range(to_day_key(utcnow()))
    return start + timedelta(hours=hour)


@respx.mock
async def test_send_creates_session_with_context_and_reply(
    session: AsyncSession, llm_env
):
    await seed_entry(session, "今天写了一篇日记", today_at())
    route = respx.post(URL)
    mock_reply(route)

    result = await send_chat_message(session, "你觉得我今天怎么样？", scope="daily", settings=llm_env)

    assert result.session.latest_sequence == 2
    assert [m.role for m in result.messages] == ["user", "assistant"]
    assert result.messages[0].content == "你觉得我今天怎么样？"
    assert result.messages[1].content == "这是模型的回答。"

    payload = request_json(route)
    assert payload["model"] == "deepseek-chat"
    assert route.calls[0].request.headers["x-opencode-session"] == "lifeos-test"
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert "今天写了一篇日记" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "你觉得我今天怎么样？"}

    count = await session.scalar(select(func.count()).select_from(ReviewChatMessage))
    assert count == 2


@respx.mock
async def test_send_includes_saved_insight_snapshot(session: AsyncSession, llm_env):
    await seed_entry(session, "今天的记录", today_at())
    start, end = day_range(to_day_key(utcnow()))
    session.add(
        AiInsight(
            id="insight-1",
            scope="daily",
            period_start=start.replace(tzinfo=None),
            period_end=end.replace(tzinfo=None),
            model="deepseek-chat",
            payload={
                "scope": "daily",
                "from": start.isoformat(),
                "to": end.isoformat(),
                "headline": "平静的一天",
                "summary": "摘要内容",
                "themes": [],
                "spending": "没有记账",
                "todos": "没有待办",
                "mood": "flat",
                "suggestion": "继续记录",
                "model": "deepseek-chat",
                "generatedAt": start.isoformat(),
            },
            created_at=start.replace(tzinfo=None),
        )
    )
    await session.commit()
    route = respx.post(URL)
    mock_reply(route)

    await send_chat_message(session, "帮我总结", scope="daily", settings=llm_env)

    system = request_json(route)["messages"][0]["content"]
    assert "平静的一天" in system
    assert "摘要内容" in system


@respx.mock
async def test_history_uses_saved_period_not_current_date(
    session: AsyncSession, llm_env
):
    old_start = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    old_chat = await create_chat_with_messages(
        session,
        scope="daily",
        period_start=old_start,
        period_end=old_start + timedelta(days=1),
        user_text="旧问题",
        assistant_text="旧回答",
    )
    await session.commit()
    await seed_entry(session, "旧周期的记录", old_start + timedelta(hours=12))
    await seed_entry(session, "今天的记录", today_at())
    route = respx.post(URL)
    mock_reply(route)

    await send_chat_message(session, "继续聊", session_id=old_chat.id, settings=llm_env)

    system = request_json(route)["messages"][0]["content"]
    assert "旧周期的记录" in system
    assert "今天的记录" not in system


@respx.mock
async def test_context_injects_only_latest_twenty_messages(
    session: AsyncSession, llm_env
):
    chat = await create_chat_with_messages(
        session,
        scope="daily",
        period_start=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
        period_end=datetime(2026, 11, 2, 0, 0, tzinfo=UTC),
        user_text="问1",
        assistant_text="答1",
    )
    for expected in range(2, 22, 2):
        await append_messages_if_current(session, chat.id, expected, f"问{expected}", f"答{expected}")
    await session.commit()
    stored = await get_chat(session, chat.id)
    assert stored is not None and stored.latest_sequence == 22
    route = respx.post(URL)
    mock_reply(route)

    await send_chat_message(session, "新问题", session_id=chat.id, settings=llm_env)

    messages = request_json(route)["messages"]
    # system + 最近 20 条历史 + 新问题
    assert len(messages) == 22
    # 共 22 条历史，最近 20 条从 sequence 3（问2）开始。
    assert messages[1]["content"] == "问2"
    assert messages[-1]["content"] == "新问题"
    # 原有 22 条 + 本轮 2 条；上下文截断不会删除历史消息。
    stored = await session.scalar(select(func.count()).select_from(ReviewChatMessage))
    assert stored == 24


@respx.mock
async def test_current_weekly_send_advances_period_end(session: AsyncSession, llm_env):
    start, _ = week_range()
    chat = await create_chat_with_messages(
        session,
        scope="weekly",
        period_start=start,
        period_end=start + timedelta(days=1),  # 周初创建时保存的旧边界
        user_text="问",
        assistant_text="答",
    )
    await session.commit()
    mock_reply(respx.post(URL))

    await send_chat_message(session, "续聊", scope="weekly", settings=llm_env)

    stored = await get_chat(session, chat.id)
    assert stored is not None
    assert stored.period_end == to_utc_naive(week_range()[1])


async def test_send_without_key_does_not_create_session(session: AsyncSession, monkeypatch):
    monkeypatch.setenv("LIFEOS_LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ChatNotConfigured):
            await send_chat_message(session, "你好", scope="daily", settings=get_settings())
    finally:
        get_settings.cache_clear()

    assert await session.scalar(select(func.count()).select_from(ReviewChatSession)) == 0
    assert await session.scalar(select(func.count()).select_from(ReviewChatMessage)) == 0


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="<html>upstream exploded sk-secret</html>"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
    ],
)
async def test_upstream_errors_are_safe_and_persist_nothing(
    session: AsyncSession, llm_env, response: httpx.Response
):
    with respx.mock:
        respx.post(URL).mock(return_value=response)
        with pytest.raises(ChatUpstreamError) as excinfo:
            await send_chat_message(session, "你好", scope="daily", settings=llm_env)

    assert "sk-secret" not in str(excinfo.value)
    assert "<html>" not in str(excinfo.value)
    assert await session.scalar(select(func.count()).select_from(ReviewChatSession)) == 0
    assert await session.scalar(select(func.count()).select_from(ReviewChatMessage)) == 0


async def test_timeout_is_wrapped_without_leaking_details(session: AsyncSession, llm_env):
    with respx.mock:
        respx.post(URL).mock(side_effect=httpx.TimeoutException("timeout"))
        with pytest.raises(ChatUpstreamError):
            await send_chat_message(session, "你好", scope="daily", settings=llm_env)

    assert await session.scalar(select(func.count()).select_from(ReviewChatSession)) == 0


@respx.mock
async def test_sequence_conflict_is_reported_without_writes(
    session: AsyncSession, llm_env, monkeypatch
):
    import app.services.review_chat as review_chat_service

    chat = await create_chat_with_messages(
        session,
        scope="daily",
        period_start=datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
        period_end=datetime(2026, 11, 2, 0, 0, tzinfo=UTC),
        user_text="问",
        assistant_text="答",
    )
    await session.commit()
    mock_reply(respx.post(URL))
    monkeypatch.setattr(review_chat_service, "append_messages_if_current", lambda *args, **kwargs: _false())

    with pytest.raises(ChatConflict):
        await send_chat_message(session, "新问题", session_id=chat.id, settings=llm_env)

    assert await session.scalar(select(func.count()).select_from(ReviewChatMessage)) == 2


async def _false():
    return False


async def test_send_to_missing_session_raises_not_found(session: AsyncSession, llm_env):
    with pytest.raises(ChatNotFound):
        await send_chat_message(session, "你好", session_id="missing", settings=llm_env)


async def test_current_and_history_reads_are_side_effect_free(session: AsyncSession):
    view = await get_current_chat(session, "daily")
    assert view.session is None
    assert view.messages == []
    assert view.stats.entry_count == 0

    chat = await create_chat_with_messages(
        session,
        scope="weekly",
        period_start=datetime(2026, 10, 26, 0, 0, tzinfo=UTC),
        period_end=datetime(2026, 11, 2, 0, 0, tzinfo=UTC),
        user_text="问",
        assistant_text="答",
    )
    await session.commit()

    history = await get_chat_session(session, chat.id, None, 100)
    assert [m.content for m in history.messages] == ["问", "答"]
    assert history.session is not None and history.session.scope == "weekly"

    page = await list_chat_sessions(session, "weekly", 10, None)
    assert [item.id for item in page.items] == [chat.id]
    assert page.next_cursor is None

    assert (await get_chat(session, chat.id)) is not None
