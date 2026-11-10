from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime

from app.api.deps import SessionDep
from app.repositories.entries import (
    create_entry as repo_create_entry,
    delete_entry as repo_delete_entry,
    get_entry,
    list_entries,
    update_entry as repo_update_entry,
)
from app.schemas import (
    EntryCreate,
    EntryListResponse,
    EntryPatch,
    EntryRead,
    Kind,
    ListQuery,
    TodoStatus,
)

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


@router.post("", response_model=EntryRead, status_code=201)
async def create_entry_route(payload: EntryCreate, session: SessionDep) -> EntryRead:
    entry = await repo_create_entry(session, payload)
    await session.commit()
    return EntryRead.model_validate(entry)


@router.patch("/{entry_id}", response_model=EntryRead)
async def update_entry_route(
    entry_id: str, payload: EntryPatch, session: SessionDep
) -> EntryRead:
    entry = await repo_update_entry(session, entry_id, payload)
    if entry is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    await session.commit()
    return EntryRead.model_validate(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_entry_route(entry_id: str, session: SessionDep) -> None:
    if not await repo_delete_entry(session, entry_id):
        raise HTTPException(status_code=404, detail="记录不存在")
    await session.commit()
