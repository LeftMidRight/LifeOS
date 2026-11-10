from alembic import command
from sqlalchemy import inspect

from tests.conftest import make_alembic_config, sync_engine


def _table_names() -> set[str]:
    with sync_engine.connect() as conn:
        return set(inspect(conn).get_table_names())


def test_review_chat_migration_downgrades_and_upgrades():
    config = make_alembic_config()
    try:
        command.downgrade(config, "0001_initial")
        assert "review_chat_sessions" not in _table_names()
        assert "review_chat_messages" not in _table_names()

        command.upgrade(config, "head")
        names = _table_names()
        assert {"review_chat_sessions", "review_chat_messages"} <= names
    finally:
        # 无论断言是否失败，都尽量把测试库恢复到 head。
        command.upgrade(config, "head")
