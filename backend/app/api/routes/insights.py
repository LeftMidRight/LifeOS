from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.core.time import day_range, to_day_key, utcnow, week_range
from app.repositories.entries import entries_in_range
from app.repositories.insights import save_insight
from app.schemas import InsightResponse
from app.services.insight import generate_insight
from app.services.stats import compute_stats

router = APIRouter(tags=["insights"])


@router.get("/insights", response_model=InsightResponse)
async def insights_route(
    session: SessionDep,
    scope: Annotated[Literal["daily", "weekly"], Query()] = "daily",
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: Annotated[AwareDatetime | None, Query()] = None,
) -> InsightResponse:
    if from_ is not None and to is not None:
        range_from, range_to = from_, to
    elif scope == "weekly":
        range_from, range_to = week_range()
    else:
        range_from, range_to = day_range(to_day_key(utcnow()))

    entries = await entries_in_range(session, range_from, range_to)
    stats = compute_stats(entries, range_from, range_to)
    result = await generate_insight(entries, stats, scope)
    await save_insight(session, result.insight)
    await session.commit()
    return InsightResponse(insight=result.insight, warning=result.warning, stats=stats)
