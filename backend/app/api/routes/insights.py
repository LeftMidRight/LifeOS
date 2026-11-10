from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.core.time import day_range, to_day_key, utcnow, week_range
from app.repositories.entries import entries_in_range
from app.repositories.insights import insight_in_range, save_insight
from app.schemas import Insight, InsightPreviewResponse, InsightResponse
from app.services.insight import (
    build_insight_payload,
    generate_insight,
    payload_text,
)
from app.services.stats import compute_stats

router = APIRouter(tags=["insights"])


def _resolve_range(
    scope: str, from_: AwareDatetime | None, to: AwareDatetime | None
):
    if from_ is not None and to is not None:
        return from_, to
    if scope == "weekly":
        return week_range()
    return day_range(to_day_key(utcnow()))


@router.get("/insights/preview", response_model=InsightPreviewResponse)
async def preview_insight(
    session: SessionDep,
    scope: Annotated[Literal["daily", "weekly"], Query()] = "daily",
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: Annotated[AwareDatetime | None, Query()] = None,
) -> InsightPreviewResponse:
    """只读预览：展示将会发送给模型的内容，不调用模型。"""
    range_from, range_to = _resolve_range(scope, from_, to)
    entries = await entries_in_range(session, range_from, range_to)
    stats = compute_stats(entries, range_from, range_to)
    payload = build_insight_payload(entries, stats, scope)
    saved = await insight_in_range(session, scope, range_from, range_to)
    return InsightPreviewResponse(
        scope=scope,
        from_=range_from,
        to=range_to,
        stats=stats,
        payload=payload,
        payload_text=payload_text(payload),
        insight=Insight.model_validate(saved.payload) if saved is not None else None,
        entry_count=len(entries),
    )


@router.get("/insights", response_model=InsightResponse)
async def insights_route(
    session: SessionDep,
    scope: Annotated[Literal["daily", "weekly"], Query()] = "daily",
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: Annotated[AwareDatetime | None, Query()] = None,
) -> InsightResponse:
    range_from, range_to = _resolve_range(scope, from_, to)

    entries = await entries_in_range(session, range_from, range_to)
    stats = compute_stats(entries, range_from, range_to)
    result = await generate_insight(entries, stats, scope)
    await save_insight(session, result.insight)
    await session.commit()
    return InsightResponse(insight=result.insight, warning=result.warning, stats=stats)
