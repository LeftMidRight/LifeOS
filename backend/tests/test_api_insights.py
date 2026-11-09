import json
from datetime import datetime, timezone

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AiInsight
from app.repositories.entries import create_entry
from app.schemas import EntryCreate

UTC = timezone.utc
URL = "https://api.deepseek.com/v1/chat/completions"
RANGE = "?scope=daily&from=2026-11-09T00:00:00.000Z&to=2026-11-10T00:00:00.000Z"


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def seed_entry(session: AsyncSession):
    entry = await create_entry(
        session,
        EntryCreate(
            kind="expense",
            content="午饭 32 元",
            amount=32,
            category="餐饮",
            occurred_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        ),
    )
    await session.commit()
    return entry


async def test_insights_without_key_falls_back(
    client: AsyncClient, session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    await seed_entry(session)

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    body = response.json()

    assert body["insight"]["model"] == "local"
    assert "未配置 LLM_API_KEY" in body["warning"]
    assert body["insight"]["headline"].startswith("今天")
    assert body["stats"]["totalSpent"] == 32.0

    count = await session.scalar(select(func.count()).select_from(AiInsight))
    assert count == 1


@respx.mock
async def test_insights_uses_model_and_saves_snapshot(
    client: AsyncClient, session: AsyncSession, llm_env
):
    await seed_entry(session)
    model_payload = {
        "headline": "今天花得不多",
        "summary": "午饭花了 32 元，状态平稳。",
        "themes": ["工作日的节奏"],
        "spending": "只有一顿午饭。",
        "todos": "没有待办。",
        "mood": "flat",
        "suggestion": "保持记录。",
    }
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_payload, ensure_ascii=False)}}]},
        )
    )

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    body = response.json()

    assert route.called
    assert body["warning"] is None
    assert body["insight"]["model"] == "deepseek-chat"
    assert body["insight"]["headline"] == "今天花得不多"
    assert body["insight"]["mood"] == "flat"

    count = await session.scalar(select(func.count()).select_from(AiInsight))
    assert count == 1


@respx.mock
async def test_insights_retries_without_json_mode_on_400(
    client: AsyncClient, session: AsyncSession, llm_env
):
    await seed_entry(session)
    payload = {
        "headline": "重试成功",
        "summary": "摘要",
        "themes": [],
        "spending": "没有记账",
        "todos": "没有待办",
        "mood": "unknown",
        "suggestion": "继续记",
    }
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(400),
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]},
            ),
        ]
    )

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    assert route.call_count == 2
    assert response.json()["insight"]["headline"] == "重试成功"


@respx.mock
async def test_insights_falls_back_on_model_failure(
    client: AsyncClient, session: AsyncSession, llm_env
):
    await seed_entry(session)
    respx.post(URL).mock(side_effect=httpx.TimeoutException("timeout"))

    response = await client.get(f"/api/insights{RANGE}")
    assert response.status_code == 200
    body = response.json()

    assert body["insight"]["model"] == "local"
    assert "模型调用失败" in body["warning"]
