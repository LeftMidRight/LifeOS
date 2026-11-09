import re

from httpx import AsyncClient

ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def test_capture_creates_expense(client: AsyncClient):
    response = await client.post(
        "/api/capture",
        json={"text": "午饭 32 元和同事", "at": "2026-11-09T15:30:00.000+08:00"},
    )
    assert response.status_code == 201
    body = response.json()

    assert body["entry"]["kind"] == "expense"
    assert body["entry"]["content"] == "午饭 32 元和同事"
    assert body["entry"]["amount"] == 32.0
    assert body["entry"]["category"] == "餐饮"
    assert body["entry"]["source"] == "capture"
    assert body["entry"]["occurredAt"] == "2026-11-09T07:30:00.000Z"
    assert ISO_Z.match(body["entry"]["occurredAt"])

    assert body["parsed"]["kind"] == "expense"
    assert body["parsed"]["amount"] == 32.0
    assert body["parsed"]["category"] == "餐饮"
    assert body["parsed"]["note"] == "记录为支出 ¥32 · 餐饮"
    assert body["parsed"]["confidence"] > 0.9


async def test_capture_todo_serializes_due_date(client: AsyncClient):
    response = await client.post(
        "/api/capture",
        json={"text": "记得明天交房租", "at": "2026-11-09T15:30:00.000+08:00"},
    )
    assert response.status_code == 201
    body = response.json()

    assert body["entry"]["kind"] == "todo"
    assert body["entry"]["status"] == "open"
    assert body["entry"]["dueAt"].endswith("Z")
    assert ISO_Z.match(body["entry"]["dueAt"])
    assert body["parsed"]["status"] == "open"
    assert body["parsed"]["content"] == "记得明天交房租"


async def test_capture_extracts_tags(client: AsyncClient):
    response = await client.post(
        "/api/capture",
        json={"text": "产品想法 #产品 #灵感", "at": "2026-11-09T15:30:00.000+08:00"},
    )
    body = response.json()
    assert body["entry"]["tags"] == ["产品", "灵感"]
    assert "#" not in body["entry"]["content"]
