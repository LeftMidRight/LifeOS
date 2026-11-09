from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text

ENTRY_COLUMNS = (
    "id", "kind", "content", "title", "occurred_at", "created_at", "updated_at",
    "amount", "currency", "category", "status", "due_at", "mood", "energy",
    "tags", "meta", "source", "deleted_at",
)

ENTRY_UPSERT = text(
    """
    INSERT INTO entries (id, kind, content, title, occurred_at, created_at, updated_at,
                         amount, currency, category, status, due_at, mood, energy,
                         tags, meta, source, deleted_at)
    VALUES (:id, :kind, :content, :title, :occurred_at, :created_at, :updated_at,
            :amount, :currency, :category, :status, :due_at, :mood, :energy,
            :tags, :meta, :source, :deleted_at)
    ON DUPLICATE KEY UPDATE
      kind=VALUES(kind), content=VALUES(content), title=VALUES(title),
      occurred_at=VALUES(occurred_at), created_at=VALUES(created_at),
      updated_at=VALUES(updated_at), amount=VALUES(amount), currency=VALUES(currency),
      category=VALUES(category), status=VALUES(status), due_at=VALUES(due_at),
      mood=VALUES(mood), energy=VALUES(energy), tags=VALUES(tags), meta=VALUES(meta),
      source=VALUES(source), deleted_at=VALUES(deleted_at)
    """
)

INSIGHT_UPSERT = text(
    """
    INSERT INTO ai_insights (id, scope, period_start, period_end, model, payload, created_at)
    VALUES (:id, :scope, :period_start, :period_end, :model, :payload, :created_at)
    ON DUPLICATE KEY UPDATE
      scope=VALUES(scope), period_start=VALUES(period_start), period_end=VALUES(period_end),
      model=VALUES(model), payload=VALUES(payload), created_at=VALUES(created_at)
    """
)


def parse_dt(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"时间缺少时区: {value}")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def parse_json(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def load_sqlite(path: Path) -> tuple[list[dict], list[dict]]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        entries = [dict(row) for row in conn.execute("SELECT * FROM entries")]
        insights = [dict(row) for row in conn.execute("SELECT * FROM ai_insights")]
    finally:
        conn.close()
    return entries, insights


def normalize_entry(row: dict) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "content": row["content"],
        "title": row.get("title"),
        "occurred_at": parse_dt(row["occurred_at"]),
        "created_at": parse_dt(row["created_at"]),
        "updated_at": parse_dt(row["updated_at"]),
        "amount": Decimal(str(row["amount"])) if row.get("amount") is not None else None,
        "currency": row.get("currency") or "CNY",
        "category": row.get("category"),
        "status": row.get("status"),
        "due_at": parse_dt(row.get("due_at")),
        "mood": row.get("mood"),
        "energy": row.get("energy"),
        "tags": json.dumps(parse_json(row.get("tags"), []), ensure_ascii=False),
        "meta": json.dumps(parse_json(row.get("meta"), {}), ensure_ascii=False),
        "source": row.get("source") or "manual",
        "deleted_at": parse_dt(row.get("deleted_at")),
    }


def normalize_insight(row: dict) -> dict:
    return {
        "id": row["id"],
        "scope": row["scope"],
        "period_start": parse_dt(row["period_start"]),
        "period_end": parse_dt(row["period_end"]),
        "model": row["model"],
        "payload": json.dumps(parse_json(row.get("payload"), {}), ensure_ascii=False),
        "created_at": parse_dt(row["created_at"]),
    }


def migrate(source: Path, target_url: str, dry_run: bool = False) -> tuple[int, int]:
    entries, insights = load_sqlite(source)
    if dry_run:
        print(f"[dry-run] entries={len(entries)} insights={len(insights)}")
        return len(entries), len(insights)

    engine = create_engine(target_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            for row in entries:
                conn.execute(ENTRY_UPSERT, normalize_entry(row))
            for row in insights:
                conn.execute(INSIGHT_UPSERT, normalize_insight(row))
    finally:
        engine.dispose()
    print(f"已迁移 entries={len(entries)} insights={len(insights)}")
    return len(entries), len(insights)


def verify(source: Path, target_url: str) -> bool:
    entries, insights = load_sqlite(source)
    engine = create_engine(target_url, pool_pre_ping=True)
    ok = True
    try:
        with engine.connect() as conn:
            target_entries = conn.execute(text("SELECT COUNT(*) FROM entries")).scalar_one()
            target_insights = conn.execute(text("SELECT COUNT(*) FROM ai_insights")).scalar_one()
            source_kinds = Counter(row["kind"] for row in entries)
            target_kinds = dict(
                conn.execute(text("SELECT kind, COUNT(*) FROM entries GROUP BY kind")).all()
            )
            source_total = sum(
                Decimal(str(row["amount"]))
                for row in entries
                if row["kind"] == "expense" and row.get("amount") is not None
            )
            target_total = conn.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM entries WHERE kind = 'expense'")
            ).scalar_one()

            checks = [
                ("entries count", len(entries), target_entries),
                ("insights count", len(insights), target_insights),
                ("kind counts", dict(source_kinds), target_kinds),
                ("expense total", source_total, Decimal(str(target_total))),
            ]
            for label, expected, actual in checks:
                matched = expected == actual
                ok = ok and matched
                print(f"{'OK ' if matched else 'FAIL'} {label}: source={expected} target={actual}")
    finally:
        engine.dispose()
    return ok


def main() -> None:
    # 直接以文件路径运行（python scripts/xxx.py）时，sys.path 只包含 scripts/，
    # 需要把 backend/ 加回来才能导入 app 包。
    if __package__ in (None, ""):
        backend_root = str(Path(__file__).resolve().parents[1])
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)

    from app.config import get_settings

    parser = argparse.ArgumentParser(description="把 data/lifeos.db 迁移到 MySQL")
    parser.add_argument("--sqlite", default="data/lifeos.db", help="SQLite 文件路径（相对仓库根目录）")
    parser.add_argument("--database-url", default=None, help="目标 MySQL URL；默认取 .env")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument("--verify", action="store_true", help="迁移后逐表核对")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / args.sqlite).resolve()
    if not source.exists():
        raise SystemExit(f"找不到 SQLite 文件: {source}")

    target = args.database_url or get_settings().lifeos_database_url.replace("+aiomysql", "+pymysql")
    migrate(source, target, dry_run=args.dry_run)
    if args.verify and not args.dry_run:
        if not verify(source, target):
            sys.exit(1)


if __name__ == "__main__":
    main()
