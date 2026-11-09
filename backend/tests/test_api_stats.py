import re
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.entries import create_entry
from app.schemas import EntryCreate

UTC = timezone.utc
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


async def test_stats_aggregates_and_serializes(client: AsyncClient, session: AsyncSession):
    rows = [
        dict(kind="expense", content="午饭", amount=32, category="餐饮", mood=4),
        dict(kind="expense", content="咖啡", amount=18, category="餐饮", mood=2),
        dict(kind="expense", content="打车", amount=48, category="交通"),
        dict(kind="todo", content="写周报", status="done"),
        dict(kind="todo", content="交房租", status="open"),
        dict(kind="journal", content="今天还不错"),
    ]
    for row in rows:
        await create_entry(
            session,
            EntryCreate(occurred_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC), **row),
        )
    await session.commit()

    response = await client.get(
        "/api/stats?from=2026-11-09T00:00:00.000Z&to=2026-11-10T00:00:00.000Z"
    )
    assert response.status_code == 200
    body = response.json()

    assert body["totalSpent"] == 98.0
    assert body["entryCount"] == 6
    assert body["openTodos"] == 1
    assert body["doneTodos"] == 1
    assert body["avgMood"] == 3.0
    assert body["byKind"] == {"expense": 3, "todo": 2, "journal": 1}
    assert body["byCategory"][0] == {"category": "餐饮", "total": 50.0, "count": 2}
    assert body["byCategory"][1] == {"category": "交通", "total": 48.0, "count": 1}
    assert ISO_Z.match(body["from"])
    assert ISO_Z.match(body["to"])


async def test_stats_excludes_soft_deleted(client: AsyncClient, session: AsyncSession):
    from app.repositories.entries import delete_entry

    entry = await create_entry(
        session,
        EntryCreate(
            kind="expense",
            content="午饭",
            amount=32,
            category="餐饮",
            occurred_at=datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        ),
    )
    await session.commit()
    await delete_entry(session, entry.id)
    await session.commit()

    response = await client.get(
        "/api/stats?from=2026-11-09T00:00:00.000Z&to=2026-11-10T00:00:00.000Z"
    )
    assert response.json()["entryCount"] == 0
    assert response.json()["totalSpent"] == 0
