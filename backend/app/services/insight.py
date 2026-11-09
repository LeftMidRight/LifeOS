from app.config import Settings


def llm_status(settings: Settings) -> dict[str, object]:
    return {
        "configured": bool(settings.llm_api_key),
        "model": settings.llm_model,
        "baseUrl": settings.llm_base_url,
    }
