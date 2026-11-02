"""Validate reviewer verdicts and merge them into a ranked result.

Reviewers read untrusted posting text, so what they return is untrusted too: every
field is type-checked and bounded, scores and bands are recomputed here, and any
free text is cleaned and dropped if it looks like an instruction.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..guard import guard_plain
from .freshness import freshness_flags
from .rubric import DIMENSIONS, GATE_VALUES, GATES, band, overall_score

MAX_ITEMS = 3
MAX_TEXT_CHARS = 160
_REVIEW_FLAG = "评审文本含可疑内容，已移除"
_CARRIED = ("key", "title", "company", "location", "url", "source", "posted_date", "deadline", "remote",
            "skills", "rule_score", "guard")


class _Invalid(Exception):
    """A review that cannot be used; the message says why."""


def _clean_text(value: Any) -> Tuple[str, bool]:
    """Return ``(text, suspicious)``; suspicious text is replaced by an empty string."""
    if not isinstance(value, str):
        return "", False
    checked = guard_plain(value)
    if checked.flagged:
        return "", True
    return checked.text[:MAX_TEXT_CHARS], False


def _clean_list(value: Any) -> Tuple[List[str], bool]:
    if not isinstance(value, list):
        return [], False
    out: List[str] = []
    suspicious = False
    for item in value:
        text, bad = _clean_text(item)
        suspicious = suspicious or bad
        if text:
            out.append(text)
        if len(out) == MAX_ITEMS:
            break
    return out, suspicious


def _score(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _Invalid("分数必须是有限数字")
    return float(min(100.0, max(0.0, value)))


def _scores(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, dict):
        raise _Invalid("缺少 scores 对象")
    missing = [name for name, _ in DIMENSIONS if name not in raw]
    if missing:
        raise _Invalid(f"scores 缺少 {', '.join(missing)}")
    return {name: _score(raw[name]) for name, _ in DIMENSIONS}


def _gate(value: Any) -> str:
    if value is None:
        return "PASS"
    upper = value.upper() if isinstance(value, str) else ""
    return upper if upper in GATE_VALUES else "FLAG"


def _deadline(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat() if len(value) == 10 else None
    except ValueError:
        return None


def _parse_review(raw: Dict[str, Any]) -> Dict[str, Any]:
    scores = _scores(raw.get("scores"))
    notes_raw = raw.get("gate_notes") if isinstance(raw.get("gate_notes"), dict) else {}
    suspicious = False
    notes: Dict[str, str] = {}
    for gate in GATES:
        text, bad = _clean_text(notes_raw.get(gate))
        suspicious = suspicious or bad
        if text:
            notes[gate] = text
    strengths, bad_s = _clean_list(raw.get("strengths"))
    gaps, bad_g = _clean_list(raw.get("gaps"))
    return {
        "scores": scores,
        "gates": {gate: _gate(raw.get(gate)) for gate in GATES},
        "gate_notes": notes,
        "strengths": strengths,
        "gaps": gaps,
        "deadline": _deadline(raw.get("deadline")),
        "suspicious": suspicious or bad_s or bad_g,
    }


def _flags(job: Mapping[str, Any], review: Mapping[str, Any]) -> List[str]:
    flags = [f"{gate}: {review['gate_notes'].get(gate) or '需人工确认'}"
             for gate, value in review["gates"].items() if value == "FLAG"]
    if str(job.get("guard") or "clean") != "clean":
        flags.append("内容安全: 岗位文本含可疑内容，已清洗后评分，请人工核对原帖")
    if review["suspicious"]:
        flags.append(_REVIEW_FLAG)
    return flags


def _item(job: Mapping[str, Any], review: Mapping[str, Any], today: date) -> Dict[str, Any]:
    overall = overall_score(review["scores"])
    failed = [f"{gate}: {review['gate_notes'].get(gate) or '不满足'}"
              for gate, value in review["gates"].items() if value == "FAIL"]
    # A deadline read from the posting's own markup outranks the reviewer's guess.
    deadline = job.get("deadline") or review["deadline"]
    expired, timing = freshness_flags(job.get("posted_date"), deadline, today)
    if expired:
        failed.append(f"已过截止日 {deadline}")
    item = {key: job.get(key) for key in _CARRIED}
    item.update(
        scores=review["scores"], overall=overall, band=band(overall), gates=review["gates"],
        gate_notes=review["gate_notes"],
        strengths=review["strengths"], gaps=review["gaps"], deadline=deadline,
        flags=_flags(job, review) + timing, excluded_reasons=failed,
    )
    return item


def _unwrap(reviews: Any) -> Tuple[List[Any], Optional[str]]:
    if isinstance(reviews, dict) and "reviews" in reviews:
        reviews = reviews["reviews"]
    if isinstance(reviews, list):
        return reviews, None
    return [], "评审结果必须是 JSON 数组"


def _collect(known: Mapping[str, Any], reviews: List[Any], issues: List[str]) -> Dict[str, Dict[str, Any]]:
    accepted: Dict[str, Dict[str, Any]] = {}
    for index, raw in enumerate(reviews, start=1):
        key = raw.get("key") if isinstance(raw, dict) else None
        if not isinstance(key, str) or key not in known:
            issues.append(f"评审 #{index} 的 key 未知或缺失，已忽略")
            continue
        if key in accepted:
            issues.append(f"重复评审 key {key}，只采用第一条")
            continue
        try:
            accepted[key] = _parse_review(raw)
        except _Invalid as exc:
            issues.append(f"评审 {key} 无效：{exc}")
    return accepted


def merge_reviews(packet: Mapping[str, Any], reviews: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """Combine a review packet with reviewer output into ranked, excluded and unreviewed lists."""
    today = today or date.today()
    jobs = {job["key"]: job for job in packet.get("jobs", [])}
    issues: List[str] = []
    items, problem = _unwrap(reviews)
    if problem:
        issues.append(problem)
    accepted = _collect(jobs, items, issues)

    ranked, excluded = [], []
    for key, review in accepted.items():
        item = _item(jobs[key], review, today)
        (excluded if item["excluded_reasons"] else ranked).append(item)
    ranked.sort(key=lambda i: (-i["overall"], -(i["rule_score"] or 0), i["title"] or ""))
    excluded.sort(key=lambda i: (-i["overall"], i["title"] or ""))

    unreviewed = sorted(
        ({k: job.get(k) for k in _CARRIED} for key, job in jobs.items() if key not in accepted),
        key=lambda i: (-(i["rule_score"] or 0), i["title"] or ""),
    )
    return {
        "ranked": ranked, "excluded": excluded, "unreviewed": unreviewed, "issues": issues,
        "fetch_issues": [i for i in packet.get("fetch_issues", []) if isinstance(i, dict)],
        "summary": {"total": len(jobs), "ranked": len(ranked), "excluded": len(excluded),
                    "unreviewed": len(unreviewed)},
    }
