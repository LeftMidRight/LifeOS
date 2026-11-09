from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_tables_exist(db_engine: AsyncEngine):
    async with db_engine.connect() as conn:
        names = await conn.run_sync(lambda sync: inspect(sync).get_table_names())
    assert {"entries", "ai_insights"} <= set(names)


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
