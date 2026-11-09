from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("时间必须带时区")
    return value.astimezone(UTC).replace(tzinfo=None)


def to_iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def _local_tz():
    return datetime.now().astimezone().tzinfo


def to_day_key(value: datetime) -> str:
    local = value.astimezone(_local_tz())
    return f"{local.year:04d}-{local.month:02d}-{local.day:02d}"


def day_range(day_key: str) -> tuple[datetime, datetime]:
    year, month, day = (int(part) for part in day_key.split("-"))
    start = datetime(year, month, day, tzinfo=_local_tz())
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def month_range(month_key: str) -> tuple[datetime, datetime]:
    year, month = (int(part) for part in month_key.split("-"))
    start = datetime(year, month, 1, tzinfo=_local_tz())
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=_local_tz())
    else:
        end = datetime(year, month + 1, 1, tzinfo=_local_tz())
    return start.astimezone(UTC), end.astimezone(UTC)


def week_range(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(_local_tz())
    local = now.astimezone(_local_tz())
    monday_offset = local.weekday()  # Monday=0
    start_local = datetime(
        local.year, local.month, local.day, tzinfo=_local_tz()
    ) - timedelta(days=monday_offset)
    end_local = datetime(local.year, local.month, local.day, tzinfo=_local_tz()) + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def add_days(value: datetime, days: int) -> datetime:
    return value + timedelta(days=days)


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1)


def to_date(value: datetime) -> date:
    return value.astimezone(_local_tz()).date()
