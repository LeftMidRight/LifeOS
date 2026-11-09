from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.entries import (
    create_entry,
    delete_entry,
    get_entry,
    list_entries,
    update_entry,
)
from app.schemas import EntryCreate, EntryPatch, ListQuery

UTC = timezone.utc


def make_entry(**overrides) -> EntryCreate:
    data = {
        "kind": "journal",
        "content": "测试记录",
        "occurred_at": datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
        "tags": [],
    }
    data.update(overrides)
    return EntryCreate(**data)


@pytest.mark.parametrize(
    "field_name", ["kind", "content", "occurred_at", "currency", "tags", "meta"]
)
def test_patch_rejects_explicit_null_for_non_nullable_fields(field_name: str):
    with pytest.raises(ValidationError):
        EntryPatch(**{field_name: None})


def test_patch_accepts_fully_omitted_fields():
    patch = EntryPatch()
    assert patch.model_fields_set == set()


def test_patch_rejects_explicit_null_via_camel_case_alias():
    with pytest.raises(ValidationError):
        EntryPatch.model_validate({"occurredAt": None})


async def test_create_and_get_entry(session: AsyncSession):
    entry = await create_entry(session, make_entry())
    await session.commit()

    fetched = await get_entry(session, entry.id)
    assert fetched is not None
    assert fetched.content == "测试记录"
    assert fetched.occurred_at == datetime(2026, 11, 9, 12, 0)


async def test_patch_keeps_missing_fields_and_sets_explicit_null(session: AsyncSession):
    entry = await create_entry(
        session,
        make_entry(title="标题", category="餐饮", amount=32, kind="expense"),
    )
    await session.commit()

    await update_entry(session, entry.id, EntryPatch(content="只改内容"))
    await session.commit()
    fetched = await get_entry(session, entry.id)
    assert fetched is not None
    assert fetched.content == "只改内容"
    assert fetched.title == "标题"
    assert fetched.category == "餐饮"
    assert float(fetched.amount) == 32.0

    await update_entry(session, entry.id, EntryPatch(title=None, amount=None, category=None))
    await session.commit()
    fetched = await get_entry(session, entry.id)
    assert fetched is not None
    assert fetched.title is None
    assert fetched.amount is None
    assert fetched.category is None


async def test_soft_delete_hides_entry(session: AsyncSession):
    entry = await create_entry(session, make_entry())
    await session.commit()

    assert await delete_entry(session, entry.id) is True
    await session.commit()

    assert await get_entry(session, entry.id) is None
    items = await list_entries(session, ListQuery())
    assert items == []


async def test_list_orders_by_utc_not_string(session: AsyncSession):
    earlier = await create_entry(
        session,
        make_entry(
            content="earlier",
            occurred_at=datetime(2026, 11, 9, 9, 0, tzinfo=timezone(timedelta(hours=8))),
        ),
    )
    later = await create_entry(
        session,
        make_entry(content="later", occurred_at=datetime(2026, 11, 9, 1, 30, tzinfo=UTC)),
    )
    await session.commit()

    items = await list_entries(session, ListQuery())
    assert [item.id for item in items] == [later.id, earlier.id]


async def test_tag_filter_matches_chinese_tag(session: AsyncSession):
    tagged = await create_entry(session, make_entry(content="产品想法", tags=["产品", "灵感"]))
    await create_entry(session, make_entry(content="别的记录", tags=["生活"]))
    await session.commit()

    items = await list_entries(session, ListQuery(tag="产品"))
    assert [item.id for item in items] == [tagged.id]


async def test_list_filters_and_pagination(session: AsyncSession):
    for index in range(3):
        await create_entry(
            session,
            make_entry(
                kind="expense",
                content=f"午饭 {index}",
                amount=index + 1,
                category="餐饮",
                occurred_at=datetime(2026, 11, 9, 12, index, tzinfo=UTC),
            ),
        )
    await session.commit()

    first = await list_entries(session, ListQuery(kind="expense", limit=2, offset=0))
    second = await list_entries(session, ListQuery(kind="expense", limit=2, offset=2))
    assert len(first) == 2
    assert len(second) == 1
    assert all(item.kind == "expense" for item in first + second)

    searched = await list_entries(session, ListQuery(q="午饭 1"))
    assert len(searched) == 1
