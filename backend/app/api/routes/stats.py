from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.repositories.entries import entries_in_range
from app.schemas import Stats
from app.services.stats import compute_stats

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=Stats)
async def stats_route(
    session: SessionDep,
    from_: Annotated[AwareDatetime, Query(alias="from")],
    to: Annotated[AwareDatetime, Query()],
) -> Stats:
    entries = await entries_in_range(session, from_, to)
    return compute_stats(entries, from_, to)
