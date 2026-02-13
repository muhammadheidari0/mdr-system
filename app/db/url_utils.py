from __future__ import annotations

from pathlib import Path


def normalize_database_url(url: str) -> str:
    """
    Normalize DB URL for tools/CLIs while preserving explicit URLs.

    - `postgresql+psycopg://...` -> unchanged
    - `sqlite:///...` -> unchanged (slashes normalized)
    - bare filesystem path -> converted to absolute sqlite URL
    """
    value = str(url or "").strip()
    if not value:
        raise ValueError("DATABASE_URL is empty. Set it in environment.")

    if "://" in value:
        if value.startswith("sqlite:///"):
            return value.replace("\\", "/")
        return value

    path = Path(value).expanduser().resolve()
    return f"sqlite:///{path.as_posix()}"
