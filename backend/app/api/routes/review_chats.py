from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import SessionDep
from app.models import ReviewChatMessage, ReviewChatSession
from app.schemas import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatSendResponse,
    ChatSessionListResponse,
    ChatSessionRead,
    ChatSessionSummary,
    ChatViewResponse,
)
from app.services.review_chat import (
    ChatConflict,
    ChatNotConfigured,
    ChatNotFound,
    ChatUpstreamError,
    ChatView,
    delete_chat_session,
    get_chat_session,
    get_current_chat,
    list_chat_sessions,
    send_chat_message,
)

router = APIRouter(tags=["review-chats"])


def _session(chat: ReviewChatSession) -> ChatSessionRead:
    return ChatSessionRead(
        id=chat.id,
        scope=chat.scope,
        period_start=chat.period_start,
        period_end=chat.period_end,
        message_count=chat.latest_sequence,
        updated_at=chat.updated_at,
        created_at=chat.created_at,
        latest_sequence=chat.latest_sequence,
    )


def _summary(chat: ReviewChatSession, message_count: int) -> ChatSessionSummary:
    return ChatSessionSummary(
        id=chat.id,
        scope=chat.scope,
        period_start=chat.period_start,
        period_end=chat.period_end,
        message_count=message_count,
        updated_at=chat.updated_at,
    )


def _message(row: ReviewChatMessage) -> ChatMessageRead:
    return ChatMessageRead(
        id=row.id,
        session_id=row.session_id,
        sequence=row.sequence,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
    )


def _view(view: ChatView) -> ChatViewResponse:
    return ChatViewResponse(
        session=_session(view.session) if view.session is not None else None,
        messages=[_message(row) for row in view.messages],
        has_more=view.has_more,
        before_sequence=view.before_sequence,
        insight=view.insight,
        stats=view.stats,
    )


def _raise_http(error: Exception) -> None:
    if isinstance(error, ChatNotConfigured):
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(error, ChatNotFound):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, ChatConflict):
        raise HTTPException(status_code=409, detail=str(error)) from error
    if isinstance(error, ChatUpstreamError):
        raise HTTPException(status_code=502, detail=str(error)) from error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=400, detail=str(error)) from error
    raise error


@router.get("/review-chats", response_model=ChatSessionListResponse)
async def list_review_chats(
    session: SessionDep,
    scope: Annotated[Literal["daily", "weekly", "all"], Query()] = "daily",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> ChatSessionListResponse:
    try:
        page = await list_chat_sessions(session, scope, limit, cursor)
    except ValueError as error:
        _raise_http(error)
    return ChatSessionListResponse(
        items=[_summary(item, page.message_counts.get(item.id, 0)) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/review-chats/current", response_model=ChatViewResponse)
async def current_review_chat(
    session: SessionDep,
    scope: Annotated[Literal["daily", "weekly"], Query()] = "daily",
) -> ChatViewResponse:
    return _view(await get_current_chat(session, scope))


@router.post("/review-chats/messages", response_model=ChatSendResponse)
async def send_review_chat_message(
    payload: ChatMessageCreate,
    session: SessionDep,
) -> ChatSendResponse:
    try:
        result = await send_chat_message(
            session,
            payload.message,
            scope=payload.scope,
            session_id=payload.session_id,
        )
    except (ChatNotConfigured, ChatNotFound, ChatConflict, ChatUpstreamError, ValueError) as error:
        _raise_http(error)
    return ChatSendResponse(
        session=_session(result.session),
        messages=[_message(row) for row in result.messages],
    )


@router.delete("/review-chats/{session_id}", status_code=204, response_class=Response)
async def delete_review_chat(session: SessionDep, session_id: str) -> Response:
    deleted = await delete_chat_session(session, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在")
    await session.commit()
    return Response(status_code=204)


@router.get("/review-chats/{session_id}", response_model=ChatViewResponse)
async def review_chat_detail(
    session: SessionDep,
    session_id: str,
    before_sequence: Annotated[int | None, Query(alias="beforeSequence", ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> ChatViewResponse:
    try:
        view = await get_chat_session(session, session_id, before_sequence, limit)
    except ChatNotFound as error:
        _raise_http(error)
    return _view(view)
