"""Validate the candidate profile Claude extracts from the user's description."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from ..parsers import parse_user_query

JLPT_LEVELS = ("N1", "N2", "N3", "N4", "N5")
REMOTE_PREFERENCES = ("only", "prefer")
VISA_STATUSES = ("needs_sponsorship", "has_work_visa", "unknown")

_LIST_LIMITS = {  # field -> (max items, max chars per item)
    "target_roles": (10, 60),
    "skills": (30, 40),
    "locations": (10, 40),
    "keyword_terms": (20, 60),
    "deal_breakers": (10, 120),
}
_MAX_RAW_QUERY, _MAX_NOTES, _MAX_ENGLISH = 2000, 500, 40
_MAX_YEARS = 60


def _clean_list(value: Any, max_items: int, max_chars: int) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    seen = set()
    out: List[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split())[:max_chars]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
        if len(out) == max_items:
            break
    return out


def _clean_text(value: Any, max_chars: int) -> str:
    return " ".join(value.split())[:max_chars] if isinstance(value, str) else ""


def _choice(value: Any, allowed: tuple, default: Any) -> Any:
    return value if isinstance(value, str) and value in allowed else default


def _years(value: Any) -> Optional[int]:
    ok = isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= _MAX_YEARS
    return value if ok else None


def normalize_profile(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a fresh, bounded profile; invalid fields fall back to the regex parse of ``raw_query``."""
    raw_query = _clean_text(data.get("raw_query"), _MAX_RAW_QUERY)
    base = parse_user_query(raw_query) if raw_query else {}
    profile: Dict[str, Any] = {
        "raw_query": raw_query,
        "remote_preference": _choice(data.get("remote_preference"), REMOTE_PREFERENCES,
                                     base.get("remote_preference")),
        "jlpt_level": _choice(data.get("jlpt_level"), JLPT_LEVELS, base.get("jlpt_level")),
        "is_chinese_speaker": data["is_chinese_speaker"] if isinstance(data.get("is_chinese_speaker"), bool)
        else bool(base.get("is_chinese_speaker", False)),
        "visa_status": _choice(data.get("visa_status"), VISA_STATUSES, "unknown"),
        "english_level": _clean_text(data.get("english_level"), _MAX_ENGLISH),
        "years_experience": _years(data.get("years_experience")),
        "notes": _clean_text(data.get("notes"), _MAX_NOTES),
    }
    for field, (max_items, max_chars) in _LIST_LIMITS.items():
        cleaned = _clean_list(data.get(field), max_items, max_chars)
        fallback = _clean_list(base.get(field, []), max_items, max_chars) or []
        profile[field] = cleaned if cleaned is not None else fallback
    return profile


def load_profile_json(text: str) -> Dict[str, Any]:
    """Parse JSON text into a profile dict; raises ``ValueError`` if it is not a JSON object."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"画像 JSON 无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("画像必须是 JSON 对象。")
    return normalize_profile(data)
