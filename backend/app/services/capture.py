from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.schemas import Kind

Category = Literal["餐饮", "交通", "购物", "住房", "娱乐", "医疗", "学习", "其他"]

PREFIXES: list[tuple[re.Pattern[str], Kind]] = [
    (re.compile(r"^(?:todo|todos|task|待办|任务|要做)\s*[:：]\s*", re.IGNORECASE), "todo"),
    (re.compile(r"^(?:支出|记账|花费|消费|花了)\s*[:：]\s*"), "expense"),
    (re.compile(r"^(?:日记|日志)\s*[:：]\s*"), "journal"),
    (re.compile(r"^(?:闪念|想法|念头|灵感)\s*[:：]\s*"), "thought"),
]

CATEGORY_KEYWORDS: list[tuple[Category, list[str]]] = [
    ("餐饮", [
        "吃", "饭", "早餐", "午餐", "晚餐", "午饭", "晚饭", "夜宵", "宵夜", "咖啡",
        "奶茶", "外卖", "火锅", "烧烤", "面条", "米粉", "包子", "零食", "水果", "食堂",
        "饮料", "可乐", "啤酒", "聚餐", "下馆子",
    ]),
    ("交通", [
        "打车", "地铁", "公交", "高铁", "火车票", "机票", "加油", "停车", "滴滴",
        "单车", "油费", "过路费", "车票", "网约车", "高速",
    ]),
    ("住房", ["房租", "水电", "电费", "水费", "物业", "宽带", "燃气", "暖气", "装修"]),
    ("医疗", ["医院", "看病", "药", "挂号", "体检", "牙", "诊所", "疫苗", "医保"]),
    ("学习", ["书", "课程", "学费", "培训", "考试", "网课", "教材", "证书", "报班"]),
    ("娱乐", [
        "电影", "游戏", "演出", "演唱会", "ktv", "会员", "订阅", "剧本杀", "桌游",
        "旅游", "门票", "展览", "音乐会",
    ]),
    ("购物", [
        "买", "衣服", "裤子", "鞋", "外套", "t恤", "快递", "淘宝", "京东", "拼多多",
        "超市", "日用品", "洗发水", "纸巾", "家居", "耳机", "数码",
    ]),
]

EXPENSE_VERBS = re.compile(r"(花了|付了|支付|消费|买了|充值|缴费|交了|打车|加油|吃了|喝了|点了|下单)")
TODO_WEAK = re.compile(r"(记得|别忘了|别忘|要记得|待办|截止|ddl|提醒我)", re.IGNORECASE)
KEEP_AS_JOURNAL = re.compile(r"(今天|昨天|最近|这周|感觉|觉得|因为|所以|后来|然后|其实|好像|突然|想起)")
WEEKDAY_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 0, "天": 0}


@dataclass
class AmountHit:
    amount: float
    raw: str
    explicit: bool


@dataclass
class DueDate:
    due_at: datetime
    matched: str


@dataclass
class CaptureResult:
    kind: Kind
    content: str
    tags: list[str]
    amount: float | None
    category: Category | None
    due_at: datetime | None
    status: Literal["open"] | None
    confidence: float
    note: str


def _to_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _round_money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _format_amount(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def find_amount(text: str) -> AmountHit | None:
    match = re.search(r"(\d+(?:\.\d{1,2})?)\s*万(?:元|块)?", text, re.ASCII)
    if match:
        amount = _round_money(Decimal(match.group(1)) * 10000)
        return AmountHit(amount, match.group(0), True)

    match = re.search(r"[¥￥$]\s*(\d[\d,]*(?:\.\d{1,2})?)", text, re.ASCII)
    if match:
        return AmountHit(_to_number(match.group(1)), match.group(0), True)

    match = re.search(
        r"(\d[\d,]*(?:\.\d{1,2})?)\s*(?:元|块钱|块|人民币|rmb)", text, re.ASCII | re.IGNORECASE
    )
    if match:
        return AmountHit(_to_number(match.group(1)), match.group(0), True)

    match = re.search(
        r"(?:花了|付了|支付了?|消费了?|支出|充值了?)\s*(\d+(?:\.\d{1,2})?)", text, re.ASCII
    )
    if match:
        return AmountHit(_to_number(match.group(1)), match.group(0), True)

    return None


def find_loose_number(text: str) -> AmountHit | None:
    blocked_pattern = re.compile(
        r"(\d+(?:\.\d{1,2})?)\s*(点|分|月|日|号|年|岁|个|次|公里|km|kg|斤|天|人|杯|层|楼)",
        re.IGNORECASE | re.ASCII,
    )
    blocked = {match.start() for match in blocked_pattern.finditer(text)}

    for match in re.finditer(r"(\d+(?:\.\d{1,2})?)", text, re.ASCII):
        index = match.start()
        if index in blocked:
            continue
        around = text[max(0, index - 1): index + len(match.group(0)) + 1]
        if re.search(r"[-/.]\s*\d", around):
            continue
        return AmountHit(_to_number(match.group(1)), match.group(1), False)
    return None


def detect_category(text: str) -> Category | None:
    lowered = text.lower()
    for category, words in CATEGORY_KEYWORDS:
        if any(word.lower() in lowered for word in words):
            return category
    return None


def detect_prefix(text: str) -> tuple[Kind, str] | None:
    for pattern, kind in PREFIXES:
        match = pattern.match(text)
        if match:
            return kind, text[match.end():].strip()
    return None


def extract_tags(text: str) -> tuple[list[str], str]:
    tags: list[str] = []

    def replace(match: re.Match[str]) -> str:
        tags.append(match.group(2))
        return match.group(1)

    cleaned = re.sub(r"(^|[\s，,。、])#([\w-]{1,20})", replace, text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return list(dict.fromkeys(tags)), cleaned


def parse_due_date(text: str, now: datetime | None = None) -> DueDate | None:
    now = now or datetime.now().astimezone()
    base = now.replace(hour=9, minute=0, second=0, microsecond=0)

    def apply_hour(value: datetime) -> datetime:
        if re.search(r"(晚|夜|下午)", text):
            return value.replace(hour=20)
        if re.search(r"中午", text):
            return value.replace(hour=12)
        return value.replace(hour=9)

    relative: list[tuple[str, int]] = [
        ("大后天", 3),
        ("后天", 2),
        ("明天|明日|明早|明晚", 1),
        ("今天|今日|今晚", 0),
    ]
    for pattern, delta in relative:
        match = re.search(pattern, text)
        if match:
            return DueDate(apply_hour(base + timedelta(days=delta)), match.group(0))

    week = re.search(r"(下)?\s*(?:周|星期)([一二三四五六日天])", text)
    if week and week.group(2):
        target = WEEKDAY_MAP[week.group(2)]
        current = now.isoweekday() % 7
        delta = (target - current + 7) % 7
        if week.group(1):
            delta += 7
        return DueDate(apply_hour(base + timedelta(days=delta)), week.group(0))

    month_day = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text, re.ASCII)
    if month_day:
        month = int(month_day.group(1))
        day = int(month_day.group(2))
        try:
            candidate = now.replace(
                month=month, day=day, hour=9, minute=0, second=0, microsecond=0
            )
        except ValueError:
            return None
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if candidate < today_start:
            candidate = candidate.replace(year=candidate.year + 1)
        return DueDate(apply_hour(candidate), month_day.group(0))

    return None


def parse_capture(raw: str, now: datetime | None = None) -> CaptureResult:
    now = now or datetime.now().astimezone()
    text = raw.strip()

    prefix = detect_prefix(text)
    if prefix is not None:
        kind_hint, text = prefix
    else:
        kind_hint = None

    tags, text = extract_tags(text)
    amount_hit = find_amount(text)
    category = detect_category(text)
    expense_verb = bool(EXPENSE_VERBS.search(text))
    bare_number = None if amount_hit else find_loose_number(text)

    is_bare_amount = bool(
        re.fullmatch(r"[¥￥$]?\s*\d+(?:\.\d{1,2})?\s*(?:元|块|块钱)?", text, re.ASCII)
    )
    looks_like_expense = bool(
        amount_hit
        or is_bare_amount
        or (bare_number and (expense_verb or category) and len(text) <= 30)
    )

    if kind_hint is not None:
        kind = kind_hint
        confidence = 0.98
    elif looks_like_expense and (
        (amount_hit and amount_hit.explicit) or expense_verb or category or is_bare_amount
    ):
        kind = "expense"
        confidence = 0.94 if (amount_hit and amount_hit.explicit) else 0.75 if is_bare_amount else 0.82
    elif TODO_WEAK.search(text) or re.match(r"^(要|得|该|必须)\s*\S", text):
        kind = "todo"
        confidence = 0.8 if TODO_WEAK.search(text) else 0.66
    elif len(text) >= 40 or KEEP_AS_JOURNAL.search(text):
        kind = "journal"
        confidence = 0.68
    else:
        kind = "thought"
        confidence = 0.6

    amount = None
    if kind == "expense":
        if amount_hit is not None:
            amount = amount_hit.amount
        elif bare_number is not None:
            amount = bare_number.amount

    final_category = (category or "其他") if kind == "expense" else None

    due_at = None
    due_text = ""
    if kind == "todo":
        due = parse_due_date(text, now)
        if due is not None:
            due_at = due.due_at
            due_text = due.matched
            confidence = min(0.95, confidence + 0.1)

    if kind == "expense":
        amount_text = f" ¥{_format_amount(amount)}" if amount is not None else "（未识别到金额）"
        category_text = f" · {final_category}" if final_category else ""
        note = f"记录为支出{amount_text}{category_text}"
    elif kind == "todo":
        note = f"记为待办{'，截止「' + due_text + '」' if due_text else '，未识别截止时间'}"
    elif kind == "journal":
        note = "记为日记"
    else:
        note = "记为闪念"

    return CaptureResult(
        kind=kind,
        content=text or raw.strip(),
        tags=tags,
        amount=amount,
        category=final_category,
        due_at=due_at,
        status="open" if kind == "todo" else None,
        confidence=max(0.4, min(0.99, confidence)),
        note=note,
    )
