from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from app.config import Settings, get_settings
from app.core.time import to_iso_z, utcnow
from app.models import Entry
from app.schemas import Insight, Stats

SYSTEM_PROMPT = """你是 LifeOS 的生活记录分析助手。用户会给你一段时间内的全部记录（JSON 数组）。
你的任务是把这些碎片还原成「这个人这段时间过得怎么样」。

硬性要求：
1. 只使用记录里出现的事实，不要编造、不要推测记录中没有的事。
2. 需要举例时，引用记录里的原话片段，不要改写。
3. 语气像一个很了解他、但不奉承的老朋友：具体、克制、不说教。
4. 只输出 JSON 对象，不要 markdown 代码块，不要任何额外说明。

输出字段：
{
  "headline": "一句话概括（不超过 20 字）",
  "summary": "120-200 字的白描：做了什么、钱花在哪、待办推进得怎样、情绪如何",
  "themes": ["反复出现的主题或念头，最多 3 条，每条不超过 12 字"],
  "spending": "对消费结构的一句判断（没有记账数据就写「这段时间没有记账」）",
  "todos": "对待办推进情况的一句判断（没有待办就写「这段时间没有待办」）",
  "mood": "up | flat | down | unknown",
  "suggestion": "一条具体可执行的建议，不超过 40 字，不要空泛"
}"""


@dataclass
class InsightResult:
    insight: Insight
    warning: str | None


def llm_status(settings: Settings) -> dict[str, object]:
    return {
        "configured": bool(settings.lifeos_llm_api_key),
        "model": settings.lifeos_llm_model,
        "baseUrl": settings.lifeos_llm_base_url,
    }


def _fmt_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def _kind_label(kind: str) -> str:
    return {
        "journal": "日记",
        "thought": "闪念",
        "expense": "记账",
        "todo": "待办",
        "habit": "习惯",
        "metric": "指标",
    }.get(kind, kind)


def compact_entries(entries: list[Entry]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for entry in entries[:200]:
        item: dict[str, object] = {
            "t": to_iso_z(entry.occurred_at),
            "kind": entry.kind,
            "text": entry.content[:240],
        }
        if entry.amount is not None:
            item["amount"] = float(entry.amount)
        if entry.category:
            item["category"] = entry.category
        if entry.status:
            item["status"] = entry.status
        if entry.due_at is not None:
            item["due"] = to_iso_z(entry.due_at)
        if entry.mood is not None:
            item["mood"] = entry.mood
        if entry.tags:
            item["tags"] = entry.tags
        items.append(item)
    return items


def _stats_payload(stats: Stats) -> dict[str, object]:
    return {
        "总记录数": stats.entry_count,
        "分类计数": stats.by_kind,
        "总支出": stats.total_spent,
        "分类支出": [category.model_dump(by_alias=True) for category in stats.by_category],
        "待办": {"进行中": stats.open_todos, "已完成": stats.done_todos},
        "平均心情": stats.avg_mood,
    }


def parse_json_loose(text: str) -> dict[str, object]:
    cleaned = re.sub(r"^\s*```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start: end + 1])
        raise ValueError("模型返回的不是合法 JSON")


async def call_model(entries: list[Entry], stats: Stats, scope: str, settings: Settings) -> dict:
    payload = {
        "scope": scope,
        "from": to_iso_z(stats.from_),
        "to": to_iso_z(stats.to),
        "stats": _stats_payload(stats),
        "entries": compact_entries(entries),
    }
    body = {
        "model": settings.lifeos_llm_model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }
    url = f"{settings.lifeos_llm_base_url.rstrip('/')}/chat/completions"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {settings.lifeos_llm_api_key}",
        # OpenCode Go 等网关用它做会话路由；普通 OpenAI 兼容服务会忽略。
        "x-opencode-session": settings.lifeos_llm_session_id,
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            url,
            json={**body, "response_format": {"type": "json_object"}},
            headers=headers,
        )
        if response.status_code == 400:
            response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
        data = response.json()

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("模型返回为空")
    return parse_json_loose(content)


def _str(value: object, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def local_insight(stats: Stats, scope: str) -> Insight:
    range_label = "今天" if scope == "daily" else "这周"
    top = stats.by_category[0] if stats.by_category else None
    parts: list[str] = []

    if stats.entry_count == 0:
        parts.append(f"{range_label}还没有任何记录。")
    else:
        kinds = "、".join(
            f"{_kind_label(kind)} {count}" for kind, count in stats.by_kind.items()
        )
        parts.append(f"{range_label}记了 {stats.entry_count} 条：{kinds}。")

    if stats.total_spent > 0:
        top_text = f"，其中{top.category}最多（¥{_fmt_number(top.total)}）" if top else ""
        parts.append(f"花了 ¥{_fmt_number(stats.total_spent)}{top_text}。")

    if stats.open_todos + stats.done_todos > 0:
        parts.append(f"待办完成 {stats.done_todos} / {stats.open_todos + stats.done_todos} 条。")

    headline = f"{range_label}还是空白" if stats.entry_count == 0 else f"{range_label}记了 {stats.entry_count} 条"
    spending = (
        f"共 ¥{_fmt_number(stats.total_spent)}"
        + (f"，{top.category}占大头" if top else "")
        if stats.total_spent > 0
        else "这段时间没有记账"
    )
    todos = (
        f"完成 {stats.done_todos}，还剩 {stats.open_todos}"
        if stats.open_todos + stats.done_todos > 0
        else "这段时间没有待办"
    )
    mood = (
        "unknown"
        if stats.avg_mood is None
        else "up"
        if stats.avg_mood >= 3.6
        else "down"
        if stats.avg_mood <= 2.4
        else "flat"
    )

    return Insight(
        scope=scope,
        from_=stats.from_,
        to=stats.to,
        headline=headline,
        summary="".join(parts),
        themes=[f"消费集中在{top.category}"] if top else [],
        spending=spending,
        todos=todos,
        mood=mood,
        suggestion=(
            "待办积压了，先挑一件今天能做完的"
            if stats.open_todos > 3
            else "继续记，样本越多越能看出规律"
        ),
        model="local",
        generated_at=utcnow(),
    )


async def generate_insight(
    entries: list[Entry],
    stats: Stats,
    scope: str,
    settings: Settings | None = None,
) -> InsightResult:
    settings = settings or get_settings()
    fallback = local_insight(stats, scope)

    if not settings.lifeos_llm_api_key:
        return InsightResult(fallback, "未配置 LIFEOS_LLM_API_KEY，当前是本地统计版摘要")
    if not entries:
        return InsightResult(fallback, None)

    try:
        raw = await call_model(entries, stats, scope, settings)
        themes = raw.get("themes", [])
        insight = Insight(
            scope=scope,
            from_=stats.from_,
            to=stats.to,
            headline=_str(raw.get("headline"), fallback.headline),
            summary=_str(raw.get("summary"), fallback.summary),
            themes=[theme for theme in themes if isinstance(theme, str)][:3]
            if isinstance(themes, list)
            else [],
            spending=_str(raw.get("spending"), fallback.spending),
            todos=_str(raw.get("todos"), fallback.todos),
            mood=raw.get("mood") if raw.get("mood") in ("up", "flat", "down", "unknown") else "unknown",
            suggestion=_str(raw.get("suggestion"), fallback.suggestion),
            model=settings.lifeos_llm_model,
            generated_at=utcnow(),
        )
        return InsightResult(insight, None)
    except Exception as error:
        return InsightResult(fallback, f"模型调用失败（{error}），已退回本地统计版")
