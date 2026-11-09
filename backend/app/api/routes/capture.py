from datetime import datetime

from fastapi import APIRouter

from app.api.deps import SessionDep
from app.repositories.entries import create_entry
from app.schemas import CaptureParsed, CaptureRequest, CaptureResponse, EntryCreate, EntryRead
from app.services.capture import parse_capture

router = APIRouter(tags=["capture"])


@router.post("/capture", response_model=CaptureResponse, status_code=201)
async def capture_route(payload: CaptureRequest, session: SessionDep) -> CaptureResponse:
    now = payload.at or datetime.now().astimezone()
    parsed = parse_capture(payload.text, now)
    entry = await create_entry(
        session,
        EntryCreate(
            kind=parsed.kind,
            content=parsed.content or payload.text,
            occurred_at=now,
            amount=parsed.amount,
            currency="CNY",
            category=parsed.category,
            status=parsed.status,
            due_at=parsed.due_at,
            tags=parsed.tags,
            meta={"captureNote": parsed.note, "confidence": parsed.confidence},
            source="capture",
        ),
    )
    return CaptureResponse(
        entry=EntryRead.model_validate(entry),
        parsed=CaptureParsed.model_validate(parsed),
    )
