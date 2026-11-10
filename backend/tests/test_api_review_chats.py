from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import update

from app.config import get_settings
from app.models import ReviewChatSession
from app.repositories.review_chats import (
    append_messages_if_current,
    create_chat_with_messages,
)
from tests.conftest import TestSession

UTC = timezone.utc
URL = "https://api.deepseek.com/v1/chat/completions"


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("LIFEOS_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LIFEOS_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LIFEOS_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("LIFEOS_LLM_SESSION_ID", "lifeos-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def mock_reply(route, text: str = "模型回答"):
    return route.mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": text}}]}
        )
    )


async def seed_chat(
    scope: str = "daily",
    start: datetime = datetime(2026, 11, 1, 0, 0, tzinfo=UTC),
    user_text: str = "旧问题",
    assistant_text: str = "旧回答",
):
    async with TestSession() as session:
        chat = await create_chat_with_messages(
            session,
            scope=scope,
            period_start=start,
            period_end=start + timedelta(days=1),
            user_text=user_text,
            assistant_text=assistant_text,
        )
        # 固定活动时间，让列表排序不依赖测试执行速度。
        await session.execute(
            update(ReviewChatSession)
            .where(ReviewChatSession.id == chat.id)
            .values(updated_at=start.replace(tzinfo=None))
        )
        await session.commit()
        return chat.id


async def test_current_chat_empty_state(client: AsyncClient):
    response = await client.get("/api/review-chats/current?scope=daily")
    assert response.status_code == 200
    body = response.json()
    assert body["session"] is None
    assert body["messages"] == []
    assert body["hasMore"] is False
    assert body["insight"] is None
    assert body["stats"]["entryCount"] == 0
    assert body["stats"]["from"].endswith("Z")


@respx.mock
async def test_send_creates_current_chat_and_returns_it(client: AsyncClient, llm_env):
    mock_reply(respx.post(URL))

    response = await client.post(
        "/api/review-chats/messages", json={"scope": "daily", "message": "你好"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session"]["scope"] == "daily"
    assert body["session"]["latestSequence"] == 2
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "你好"
    assert body["messages"][1]["content"] == "模型回答"

    current = await client.get("/api/review-chats/current?scope=daily")
    current_body = current.json()
    assert current_body["session"]["id"] == body["session"]["id"]
    assert len(current_body["messages"]) == 2

    weekly = await client.get("/api/review-chats/current?scope=weekly")
    assert weekly.json()["session"] is None


@respx.mock
async def test_history_session_can_be_loaded_and_continued(client: AsyncClient, llm_env):
    chat_id = await seed_chat()
    detail = await client.get(f"/api/review-chats/{chat_id}")
    assert detail.status_code == 200
    assert [m["content"] for m in detail.json()["messages"]] == ["旧问题", "旧回答"]
    assert detail.json()["insight"] is None

    mock_reply(respx.post(URL), "继续的回答")
    response = await client.post(
        "/api/review-chats/messages", json={"sessionId": chat_id, "message": "继续"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session"]["latestSequence"] == 4
    assert [m["content"] for m in body["messages"]] == ["继续", "继续的回答"]


async def test_detail_accepts_camel_case_before_sequence(client: AsyncClient):
    chat_id = await seed_chat()
    async with TestSession() as session:
        await append_messages_if_current(session, chat_id, 2, "第二问", "第二答")
        await session.commit()

    response = await client.get(f"/api/review-chats/{chat_id}?beforeSequence=3&limit=2")
    assert response.status_code == 200
    body = response.json()
    assert [m["sequence"] for m in body["messages"]] == [1, 2]
    assert body["hasMore"] is False


async def test_missing_session_returns_404(client: AsyncClient):
    assert (await client.get("/api/review-chats/missing")).status_code == 404
    assert (await client.delete("/api/review-chats/missing")).status_code == 404


@respx.mock
async def test_message_validation_rejects_blank_and_oversized(client: AsyncClient, llm_env):
    blank = await client.post("/api/review-chats/messages", json={"scope": "daily", "message": "   "})
    assert blank.status_code == 400

    too_long = await client.post(
        "/api/review-chats/messages", json={"scope": "daily", "message": "x" * 4001}
    )
    assert too_long.status_code == 400

    no_target = await client.post(
        "/api/review-chats/messages", json={"message": "缺少 scope 和 sessionId"}
    )
    assert no_target.status_code == 400


async def test_send_without_key_returns_503(client: AsyncClient, monkeypatch):
    monkeypatch.setenv("LIFEOS_LLM_API_KEY", "")
    get_settings.cache_clear()
    try:
        response = await client.post(
            "/api/review-chats/messages", json={"scope": "daily", "message": "你好"}
        )
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
    assert "LIFEOS_LLM_API_KEY" in response.json()["error"]


@respx.mock
async def test_upstream_failure_returns_502_without_leaking_body(client: AsyncClient, llm_env):
    respx.post(URL).mock(return_value=httpx.Response(500, text="<html>sk-secret</html>"))

    response = await client.post(
        "/api/review-chats/messages", json={"scope": "daily", "message": "你好"}
    )
    assert response.status_code == 502
    assert "sk-secret" not in response.text
    assert "<html>" not in response.text


@respx.mock
async def test_sequence_conflict_returns_409(client: AsyncClient, llm_env, monkeypatch):
    import app.services.review_chat as service

    chat_id = await seed_chat()
    mock_reply(respx.post(URL))

    async def fake_append(*args, **kwargs):
        return False

    monkeypatch.setattr(service, "append_messages_if_current", fake_append)
    response = await client.post(
        "/api/review-chats/messages", json={"sessionId": chat_id, "message": "续聊"}
    )
    assert response.status_code == 409

    detail = await client.get(f"/api/review-chats/{chat_id}")
    assert detail.json()["session"]["latestSequence"] == 2


async def test_list_chats_scopes_and_pagination(client: AsyncClient):
    older = await seed_chat(scope="daily", start=datetime(2026, 11, 1, 0, 0, tzinfo=UTC))
    newer = await seed_chat(scope="weekly", start=datetime(2026, 11, 2, 0, 0, tzinfo=UTC))

    all_response = await client.get("/api/review-chats?scope=all&limit=1")
    assert all_response.status_code == 200
    first_page = all_response.json()
    assert len(first_page["items"]) == 1
    assert first_page["items"][0]["scope"] == "weekly"
    assert first_page["nextCursor"]

    second_page = await client.get(
        f"/api/review-chats?scope=all&limit=1&cursor={first_page['nextCursor']}"
    )
    assert second_page.json()["items"][0]["id"] == older

    daily = await client.get("/api/review-chats?scope=daily")
    assert [item["id"] for item in daily.json()["items"]] == [older]
    weekly = await client.get("/api/review-chats?scope=weekly")
    assert [item["id"] for item in weekly.json()["items"]] == [newer]


async def test_invalid_cursor_returns_400(client: AsyncClient):
    response = await client.get("/api/review-chats?scope=all&cursor=not-a-cursor")
    assert response.status_code == 400


@respx.mock
async def test_delete_chat_removes_only_chat_data(client: AsyncClient, llm_env):
    chat_id = await seed_chat()
    response = await client.delete(f"/api/review-chats/{chat_id}")
    assert response.status_code == 204
    assert (await client.get(f"/api/review-chats/{chat_id}")).status_code == 404
    assert (await client.delete(f"/api/review-chats/{chat_id}")).status_code == 404


@respx.mock
async def test_current_scope_mismatch_for_session_returns_409(client: AsyncClient, llm_env):
    # 历史会话（2026-11-01）不能再被当作当前周期会话续聊。
    chat_id = await seed_chat(start=datetime(2026, 11, 1, 0, 0, tzinfo=UTC))
    mock_reply(respx.post(URL))
    response = await client.post(
        "/api/review-chats/messages",
        json={"scope": "daily", "sessionId": chat_id, "message": "你好"},
    )
    assert response.status_code == 409
