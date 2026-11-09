from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.models import Entry
from app.schemas import CategoryTotal, Stats


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_stats(entries: list[Entry], from_: datetime, to: datetime) -> Stats:
    by_kind: Counter[str] = Counter()
    by_category: dict[str, dict[str, Decimal | int]] = {}
    total_spent = Decimal("0")
    open_todos = 0
    done_todos = 0
    mood_sum = 0
    mood_count = 0

    for entry in entries:
        by_kind[entry.kind] += 1
        if entry.kind == "expense":
            amount = entry.amount or Decimal("0")
            total_spent += amount
            key = entry.category or "其他"
            bucket = by_category.setdefault(key, {"total": Decimal("0"), "count": 0})
            bucket["total"] = bucket["total"] + amount
            bucket["count"] = int(bucket["count"]) + 1
        if entry.kind == "todo":
            if entry.status == "done":
                done_todos += 1
            elif entry.status == "open":
                open_todos += 1
        if entry.mood is not None:
            mood_sum += entry.mood
            mood_count += 1

    categories = [
        CategoryTotal(
            category=category,
            total=float(_money(bucket["total"])),
            count=int(bucket["count"]),
        )
        for category, bucket in by_category.items()
    ]
    categories.sort(key=lambda item: item.total, reverse=True)

    avg_mood = None
    if mood_count:
        avg_mood = float(
            (Decimal(mood_sum) / Decimal(mood_count)).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        )

    return Stats(
        from_=from_,
        to=to,
        total_spent=float(_money(total_spent)),
        by_category=categories,
        by_kind=dict(by_kind),
        open_todos=open_todos,
        done_todos=done_todos,
        avg_mood=avg_mood,
        entry_count=len(entries),
    )
