import re
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.entries import create_entry, delete_entry
from app.schemas import EntryCreate

UTC = timezone.utc
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def seed(session: AsyncSession, **overrides):
    data = {
        "kind": "journal",
        "content": "测试记录",
        "occurred_at": datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        "tags": [],
    }
    data.update(overrides)
    entry = await create_entry(session, EntryCreate(**data))
    await session.commit()
    return entry


async def test_list_entries_contract(client: AsyncClient, session: AsyncSession):
    entry = await seed(session, tags=["产品"])
    response = await client.get("/api/entries")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["id"] == entry.id
    assert item["occurredAt"].endswith("Z")
    assert ISO_Z.match(item["occurredAt"])
    assert set(item) == {
        "id", "kind", "content", "title", "occurredAt", "createdAt", "updatedAt",
        "amount", "currency", "category", "status", "dueAt", "mood", "energy",
        "tags", "meta", "source",
    }
    assert item["tags"] == ["产品"]


async def test_list_filters(client: AsyncClient, session: AsyncSession):
    await seed(session, kind="expense", content="午饭 32", amount=32, category="餐饮")
    await seed(session, kind="todo", content="交房租", status="open")
    await seed(session, kind="journal", content="今天很累", tags=["情绪"])

    expense = await client.get("/api/entries?kind=expense")
    assert expense.json()["count"] == 1

    search = await client.get("/api/entries?q=房租")
    assert search.json()["count"] == 1

    tag = await client.get("/api/entries?tag=情绪")
    assert tag.json()["count"] == 1

    paged = await client.get("/api/entries?limit=2&offset=2")
    assert paged.json()["count"] == 1


async def test_get_entry_and_404(client: AsyncClient, session: AsyncSession):
    entry = await seed(session)

    found = await client.get(f"/api/entries/{entry.id}")
    assert found.status_code == 200
    assert found.json()["id"] == entry.id

    missing = await client.get("/api/entries/not-exists")
    assert missing.status_code == 404
    assert missing.json() == {"error": "记录不存在"}


async def test_soft_deleted_entry_is_hidden(client: AsyncClient, session: AsyncSession):
    entry = await seed(session)
    await delete_entry(session, entry.id)
    await session.commit()

    listing = await client.get("/api/entries")
    assert listing.json()["count"] == 0

    detail = await client.get(f"/api/entries/{entry.id}")
    assert detail.status_code == 404
