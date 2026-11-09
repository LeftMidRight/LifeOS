from pathlib import Path


def resolve_static_file(web_dist: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    root = web_dist.resolve()
    candidate = (root / raw_path).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None
