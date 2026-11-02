"""Date normalisation for untrusted source fields."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

_DATE_CHARS = 10


def normalize_date(value: Any) -> Optional[str]:
    """Return ``YYYY-MM-DD`` from an ISO date or datetime string, else ``None``."""
    if not isinstance(value, str) or len(value) < _DATE_CHARS or len(value) > 64:
        return None
    head = value[:_DATE_CHARS]
    if len(value) > _DATE_CHARS and value[_DATE_CHARS] not in "T ":
        return None
    try:
        return date.fromisoformat(head).isoformat()
    except ValueError:
        return None
