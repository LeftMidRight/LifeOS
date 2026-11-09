from datetime import datetime, timedelta, timezone

from app.core.time import day_range, to_iso_z, to_utc_naive


def test_to_iso_z_has_milliseconds_and_z():
    value = datetime(2026, 11, 9, 9, 34, 11, 695000, tzinfo=timezone.utc)
    assert to_iso_z(value) == "2026-11-09T09:34:11.695Z"


def test_to_iso_z_treats_naive_as_utc():
    assert to_iso_z(datetime(2026, 11, 9, 9, 34, 11, 1000)) == "2026-11-09T09:34:11.001Z"


def test_to_utc_naive_converts_offset():
    value = datetime(2026, 11, 9, 21, 15, 0, tzinfo=timezone(timedelta(hours=8)))
    assert to_utc_naive(value) == datetime(2026, 11, 9, 13, 15, 0)


def test_day_range_returns_utc_bounds():
    start, end = day_range("2026-11-09")
    assert start.tzinfo is not None
    assert end.tzinfo is not None
    assert (end - start).total_seconds() == 86400
