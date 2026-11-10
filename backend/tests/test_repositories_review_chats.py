from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReviewChatMessage, ReviewChatSession
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

UTC = timezone.utc
PERIOD_START = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
PERIOD_END = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)


async def make_chat(session: AsyncSession, scope: str = "daily", start: datetime = PERIOD_START):
    chat = await create_chat_with_messages(
        session,
        scope=scope,
        period_start=start,
        period_end=start + timedelta(days=1),
        user_text="你好",
        assistant_text="你好呀",
    )
    await session.commit()
    return chat


async def test_find_chat_by_period_is_unique_and_scoped(session: AsyncSession):
    chat = await make_chat(session)
    other_start = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
    await make_chat(session, scope="weekly", start=other_start)

    found = await find_chat_by_period(session, "daily", PERIOD_START)
    assert found is not None and found.id == chat.id
    assert await find_chat_by_period(session, "weekly", PERIOD_START) is None
    assert await find_chat_by_period(session, "daily", other_start) is None


async def test_messages_are_ordered_by_sequence_not_timestamp(session: AsyncSession):
    chat = await make_chat(session)
    await append_messages_if_current(session, chat.id, 2, "第二问", "第二答")
    await session.commit()

    messages, has_more = await list_messages(session, chat.id, limit=100)
    assert [m.sequence for m in messages] == [1, 2, 3, 4]
    assert [m.content for m in messages] == ["你好", "你好呀", "第二问", "第二答"]
    assert not has_more


async def test_list_messages_pages_backwards(session: AsyncSession):
    chat = await make_chat(session)
    await append_messages_if_current(session, chat.id, 2, "第二问", "第二答")
    await session.commit()

    latest, has_more = await list_messages(session, chat.id, limit=2)
    assert [m.sequence for m in latest] == [3, 4]
    assert has_more

    older, older_more = await list_messages(session, chat.id, before_sequence=3, limit=2)
    assert [m.sequence for m in older] == [1, 2]
    assert not older_more


async def test_recent_messages_limits_to_latest_twenty(session: AsyncSession):
    chat = await make_chat(session)
    for expected in range(2, 26, 2):
        await append_messages_if_current(session, chat.id, expected, f"问{expected}", f"答{expected}")
    await session.commit()

    # 1 对初始问答 + 12 对追加 = 26 条；最近 20 条是 sequence 7..26。
    recent = await recent_messages(session, chat.id, limit=20)
    assert len(recent) == 20
    assert [m.sequence for m in recent] == list(range(7, 27))
    assert recent[0].content == "问6"
    assert recent[-1].content == "答24"


async def test_append_is_optimistic_and_atomic(session: AsyncSession):
    chat = await make_chat(session)
    chat_id = chat.id

    assert await append_messages_if_current(session, chat_id, 2, "新问", "新答") is True
    await session.commit()
    assert await append_messages_if_current(session, chat_id, 2, "过期问", "过期答") is False
    await session.rollback()

    messages, _ = await list_messages(session, chat_id, limit=100)
    assert [m.content for m in messages] == ["你好", "你好呀", "新问", "新答"]
    stored = await get_chat(session, chat_id)
    assert stored is not None and stored.latest_sequence == 4


async def test_delete_chat_cascades_messages(session: AsyncSession):
    chat = await make_chat(session)

    assert await delete_chat(session, chat.id) is True
    await session.commit()
    assert await get_chat(session, chat.id) is None
    count = await session.scalar(
        select(func.count()).select_from(ReviewChatMessage).where(ReviewChatMessage.session_id == chat.id)
    )
    assert count == 0
    assert await delete_chat(session, chat.id) is False


async def test_list_chats_orders_and_pages_by_updated_at(session: AsyncSession):
    first = await make_chat(session)
    # 固定第一条的更新时间，避免两次创建落在同一毫秒导致顺序不确定。
    await session.execute(
        update(ReviewChatSession)
        .where(ReviewChatSession.id == first.id)
        .values(updated_at=datetime(2026, 11, 9, 0, 0))
    )
    await session.commit()
    second_start = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
    second = await make_chat(session, start=second_start)

    page_one = await list_chats(session, "all", limit=1, cursor_values=None)
    assert [chat.id for chat in page_one] == [second.id]

    # 从 DB 重新读取，拿到 DATETIME(3) 精度的时间（内存对象可能带微秒）。
    await session.refresh(page_one[0])
    cursor = (page_one[0].updated_at, page_one[0].id)
    page_two = await list_chats(session, "all", limit=1, cursor_values=cursor)
    assert [chat.id for chat in page_two] == [first.id]


async def test_list_chats_hides_sessions_without_assistant_reply(session: AsyncSession):
    chat = await make_chat(session)
    empty = ReviewChatSession(
        id="empty-session",
        scope="weekly",
        period_start=PERIOD_START.replace(day=3),
        period_end=PERIOD_START.replace(day=10),
        created_at=PERIOD_START.replace(tzinfo=None),
        updated_at=PERIOD_START.replace(tzinfo=None),
        latest_sequence=0,
    )
    session.add(empty)
    await session.commit()

    chats = await list_chats(session, "all", limit=10, cursor_values=None)
    assert [item.id for item in chats] == [chat.id]
