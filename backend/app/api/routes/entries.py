from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.repositories.entries import get_entry, list_entries
from app.schemas import EntryListResponse, EntryRead, Kind, ListQuery, TodoStatus

router = APIRouter(prefix="/entries", tags=["entries"])


@router.get("", response_model=EntryListResponse)
async def list_entries_route(
    session: SessionDep,
    from_: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    to: Annotated[AwareDatetime | None, Query()] = None,
    kind: Annotated[Kind | None, Query()] = None,
    status: Annotated[TodoStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    tag: Annotated[str | None, Query(max_length=30)] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EntryListResponse:
    query = ListQuery(
        from_=from_,
        to=to,
        kind=kind,
        status=status,
        q=q,
        tag=tag,
        limit=limit,
        offset=offset,
    )
    items = await list_entries(session, query)
    return EntryListResponse(
        items=[EntryRead.model_validate(item) for item in items],
        count=len(items),
    )


@router.get("/{entry_id}", response_model=EntryRead)
async def get_entry_route(entry_id: str, session: SessionDep) -> EntryRead:
    entry = await get_entry(session, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    return EntryRead.model_validate(entry)
