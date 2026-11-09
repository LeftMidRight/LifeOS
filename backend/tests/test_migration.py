import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from app.config import get_settings
from scripts.migrate_sqlite_to_mysql import migrate, verify

SOURCE_SCHEMA = """
CREATE TABLE entries (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, content TEXT NOT NULL, title TEXT,
  occurred_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  amount REAL, currency TEXT NOT NULL DEFAULT 'CNY', category TEXT, status TEXT,
  due_at TEXT, mood INTEGER, energy INTEGER, tags TEXT NOT NULL DEFAULT '[]',
  meta TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL DEFAULT 'manual', deleted_at TEXT
);
CREATE TABLE ai_insights (
  id TEXT PRIMARY KEY, scope TEXT NOT NULL, period_start TEXT NOT NULL,
  period_end TEXT NOT NULL, model TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


def make_source(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SOURCE_SCHEMA)
    conn.execute(
        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "e1", "expense", "午饭 32", None,
            "2026-11-09T12:30:00+08:00", "2026-11-09T12:30:00+08:00", "2026-11-09T12:30:00+08:00",
            32, "CNY", "餐饮", None, None, None, None, '[]', '{}', "manual", None,
        ),
    )
    conn.execute(
        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "e2", "journal", "深夜记录", None,
            "2026-11-09T14:00:00Z", "2026-11-09T14:00:00Z", "2026-11-09T14:00:00Z",
            None, "CNY", None, None, None, None, None, '["技术"]', '{}', "manual", None,
        ),
    )
    conn.execute(
        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "e3", "todo", "已删除的待办", None,
            "2026-11-08T09:00:00+08:00", "2026-11-08T09:00:00+08:00", "2026-11-08T09:00:00+08:00",
            None, "CNY", None, "open", None, None, None, '[]', '{}', "manual",
            "2026-11-09T10:00:00+08:00",
        ),
    )
    conn.execute(
        "INSERT INTO ai_insights VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "i1", "daily", "2026-11-09T00:00:00+08:00", "2026-11-10T00:00:00+08:00",
            "local", '{"headline":"测试"}', "2026-11-09T10:00:00+08:00",
        ),
    )
    conn.commit()
    conn.close()


def test_migration_normalizes_time_and_is_idempotent(tmp_path: Path):
    source = tmp_path / "lifeos.db"
    make_source(source)
    target_url = get_settings().lifeos_test_database_url.replace("+aiomysql", "+pymysql")

    assert migrate(source, target_url) == (3, 1)
    assert migrate(source, target_url) == (3, 1)

    engine = create_engine(target_url)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM entries")).scalar_one() == 3
        assert conn.execute(text("SELECT COUNT(*) FROM ai_insights")).scalar_one() == 1
        rows = conn.execute(text("SELECT id, occurred_at FROM entries ORDER BY id")).all()
        by_id = {row.id: row.occurred_at for row in rows}
        assert by_id["e1"] == datetime(2026, 11, 9, 4, 30, 0)
        assert by_id["e2"] == datetime(2026, 11, 9, 14, 0, 0)
        assert by_id["e3"] == datetime(2026, 11, 8, 1, 0, 0)

    assert verify(source, target_url) is True
