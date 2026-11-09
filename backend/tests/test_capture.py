from datetime import datetime, timedelta, timezone

from app.services.capture import parse_capture, parse_due_date

NOW = datetime(2026, 11, 9, 15, 30, tzinfo=timezone(timedelta(hours=8)))  # 周一


def test_amount_with_unit_becomes_expense_and_category():
    result = parse_capture("午饭 32 元和同事", NOW)
    assert result.kind == "expense"
    assert result.amount == 32
    assert result.category == "餐饮"
    assert result.confidence > 0.9


def test_currency_symbol():
    result = parse_capture("打车 ¥48.5", NOW)
    assert result.kind == "expense"
    assert result.amount == 48.5
    assert result.category == "交通"


def test_wan_amount():
    result = parse_capture("交房租 1.2万", NOW)
    assert result.kind == "expense"
    assert result.amount == 12000
    assert result.category == "住房"


def test_number_plus_category_word():
    result = parse_capture("咖啡 25", NOW)
    assert result.kind == "expense"
    assert result.amount == 25


def test_explicit_prefix_wins():
    result = parse_capture("闪念：今天想到一个点子，关于记账 20 元的事", NOW)
    assert result.kind == "thought"
    assert result.amount is None


def test_reminder_becomes_todo_and_parses_tomorrow():
    result = parse_capture("记得明天交房租", NOW)
    assert result.kind == "todo"
    assert result.status == "open"
    assert result.due_at is not None
    assert result.due_at.day == 10


def test_daily_reflection_is_not_expense():
    result = parse_capture("今天天气很好，突然觉得该慢一点", NOW)
    assert result.kind != "expense"
    assert result.amount is None


def test_long_text_becomes_journal():
    result = parse_capture(
        "今天下午开了三个会，脑子有点糊。回来的路上一直在想那个架构问题，"
        "后来在地铁上突然想通了：其实不需要同步层，服务端就是唯一真相。",
        NOW,
    )
    assert result.kind == "journal"


def test_tags_are_extracted_and_removed():
    result = parse_capture("想到一个装修的点子 #装修 #灵感", NOW)
    assert result.tags == ["装修", "灵感"]
    assert "#" not in result.content


def test_due_date_month_day():
    due = parse_due_date("11月20日交房租", NOW)
    assert due is not None
    assert due.due_at.month == 11
    assert due.due_at.day == 20


def test_due_date_weekday_and_next_week():
    this_week = parse_due_date("周三开会", NOW)
    next_week = parse_due_date("下周三开会", NOW)
    assert this_week is not None
    assert next_week is not None
    assert this_week.due_at.weekday() == 2
    assert next_week.due_at.weekday() == 2
    assert next_week.due_at > this_week.due_at


def test_clock_time_is_not_amount():
    result = parse_capture("今天 3点 开会", NOW)
    assert result.kind != "expense"
    assert result.amount is None


def test_bare_number_is_expense():
    result = parse_capture("32", NOW)
    assert result.kind == "expense"
    assert result.amount == 32


def test_chinese_tags_and_deduplication():
    result = parse_capture("产品想法 #产品 #产品 #灵感", NOW)
    assert result.tags == ["产品", "灵感"]


def test_todo_prefix_strips_prefix():
    result = parse_capture("todo: 预约牙医", NOW)
    assert result.kind == "todo"
    assert result.content == "预约牙医"


def test_expense_note_is_human_readable():
    result = parse_capture("午饭 32 元", NOW)
    assert result.note == "记录为支出 ¥32 · 餐饮"
