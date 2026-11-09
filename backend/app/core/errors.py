from fastapi.exceptions import RequestValidationError


def format_validation_detail(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = [
            str(item)
            for item in error.get("loc", ())
            if item not in ("body", "query", "path")
        ]
        field = ".".join(location) or "参数"
        parts.append(f"{field}：{error.get('msg', '不合法')}")
    return "；".join(parts)
