"""Staleness and deadline flags for postings."""
from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple

STALE_AFTER_DAYS = 30
URGENT_WITHIN_DAYS = 7


def _parse(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(value[:10]) if isinstance(value, str) else None
    except ValueError:
        return None


def freshness_flags(posted: Optional[str], deadline: Optional[str], today: date) -> Tuple[bool, List[str]]:
    """Return ``(expired, flags)``; an unparsable date is ignored rather than guessed."""
    flags: List[str] = []
    due = _parse(deadline)
    if due is not None:
        remaining = (due - today).days
        if remaining < 0:
            return True, flags
        if remaining == 0:
            flags.append("🔥 今天截止")
        elif remaining <= URGENT_WITHIN_DAYS:
            flags.append(f"🔥 距截止还有 {remaining} 天")
    posted_on = _parse(posted)
    if posted_on is not None and (today - posted_on).days > STALE_AFTER_DAYS:
        flags.append(f"发布于 {(today - posted_on).days} 天前，可能已过时")
    return False, flags
