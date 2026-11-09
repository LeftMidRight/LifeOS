from fastapi import APIRouter, Request

from app.core.time import to_iso_z, utcnow
from app.services.insight import llm_status

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "ok": True,
        "version": "0.2.0",
        "db": settings.safe_database_url,
        "llm": llm_status(settings),
        "now": to_iso_z(utcnow()),
    }
