from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_tables_exist(db_engine: AsyncEngine):
    async with db_engine.connect() as conn:
        names = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
    assert {"entries", "ai_insights"} <= set(names)


async def test_review_chat_tables_and_constraints(db_engine: AsyncEngine):
    async with db_engine.connect() as conn:
        schema = await conn.run_sync(
            lambda sync: {
                "session_columns": {c["name"] for c in inspect(sync).get_columns("review_chat_sessions")},
                "message_columns": {c["name"] for c in inspect(sync).get_columns("review_chat_messages")},
                "session_uniques": [
                    u["column_names"] for u in inspect(sync).get_unique_constraints("review_chat_sessions")
                ],
                "message_uniques": [
                    u["column_names"] for u in inspect(sync).get_unique_constraints("review_chat_messages")
                ],
                "message_fks": inspect(sync).get_foreign_keys("review_chat_messages"),
            }
        )
        table_options = (
            await conn.execute(
                text(
                    "SELECT TABLE_NAME, ENGINE, TABLE_COLLATION FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME IN ('review_chat_sessions', 'review_chat_messages')"
                )
            )
        ).all()

    assert {
        "id",
        "scope",
        "period_start",
        "period_end",
        "created_at",
        "updated_at",
        "latest_sequence",
    } <= schema["session_columns"]
    assert {"id", "session_id", "sequence", "role", "content", "created_at"} <= schema["message_columns"]
    assert ["scope", "period_start"] in schema["session_uniques"]
    assert ["session_id", "sequence"] in schema["message_uniques"]
    assert any(
        fk["referred_table"] == "review_chat_sessions" and fk["options"].get("ondelete") == "CASCADE"
        for fk in schema["message_fks"]
    )
    assert {row.TABLE_NAME for row in table_options} == {
        "review_chat_sessions",
        "review_chat_messages",
    }
    for row in table_options:
        assert row.ENGINE == "InnoDB"
        assert row.TABLE_COLLATION.startswith("utf8mb4")



async def test_entries_columns_and_indexes(db_engine: AsyncEngine):
    async with db_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync: {column["name"] for column in inspect(sync).get_columns("entries")}
        )
        indexes = await conn.run_sync(
            lambda sync: {index["name"] for index in inspect(sync).get_indexes("entries")}
        )

    assert {"id", "kind", "content", "occurred_at", "amount", "tags", "meta", "deleted_at"} <= columns
    assert {"idx_entries_occurred", "idx_entries_kind", "idx_entries_status"} <= indexes
