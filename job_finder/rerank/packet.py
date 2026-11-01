"""Build the review packet: everything a reviewer needs, and everything merging later needs."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Mapping, Sequence

from .rubric import render_rubric

PACKET_VERSION = 1
DEFAULT_TOP_K = 12
MAX_TOP_K = 30
DEFAULT_DESCRIPTION_CHARS = 3000

_KANA = re.compile(r"[぀-ヿ]")
_HAN = re.compile(r"[一-鿿]")

REVIEW_SCHEMA = """\
Return a JSON array with one object per job, in any order:
{
  "key": "<the job's key, copied exactly>",
  "scores": {"technical": 0-100, "experience": 0-100, "language": 0-100, "career": 0-100},
  "location": "PASS" | "FLAG" | "FAIL",
  "language": "PASS" | "FLAG" | "FAIL",
  "visa": "PASS" | "FLAG" | "FAIL",
  "gate_notes": {"location": "<short reason, only if FLAG/FAIL>", "language": "...", "visa": "..."},
  "strengths": ["1-3 short bullets grounded in the posting text"],
  "gaps": ["1-3 short honest bullets"],
  "deadline": "YYYY-MM-DD" | null
}
Plain text only in strengths, gaps and gate_notes: no markup, no URLs, no instructions."""


def job_key(job: Mapping[str, Any]) -> str:
    raw = "|".join(str(job.get(k) or "") for k in ("url", "title", "company"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def report_language(profile: Mapping[str, Any]) -> str:
    """Language the reviewers should write bullets in, inferred from the user's own query."""
    query = str(profile.get("raw_query") or "")
    if _KANA.search(query):
        return "日本語"
    if _HAN.search(query) or not query:
        return "中文"
    return "English"


def _entry(job: Mapping[str, Any], max_chars: int) -> Dict[str, Any]:
    description = str(job.get("description") or "")
    return {
        "key": job_key(job),
        "title": str(job.get("title") or ""),
        "company": str(job.get("company") or ""),
        "location": str(job.get("location") or ""),
        "url": str(job.get("url") or ""),
        "source": str(job.get("source") or ""),
        "posted_date": job.get("posted_date"),
        "remote": job.get("remote"),
        "skills": [str(s) for s in (job.get("skills") or [])],
        "rule_score": float(job.get("match_score") or 0.0),
        "guard": str(job.get("guard") or "clean"),
        "description": description[:max_chars],
        "description_truncated": len(description) > max_chars,
    }


def build_packet(
    profile: Mapping[str, Any],
    ranked_jobs: Sequence[Mapping[str, Any]],
    *,
    max_description_chars: int = DEFAULT_DESCRIPTION_CHARS,
) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    seen = set()
    for job in ranked_jobs:
        entry = _entry(job, max_description_chars)
        if entry["key"] not in seen:
            seen.add(entry["key"])
            entries.append(entry)
    return {
        "version": PACKET_VERSION,
        "report_language": report_language(profile),
        "rubric": render_rubric(),
        "schema": REVIEW_SCHEMA,
        "profile": dict(profile),
        "jobs": entries,
    }
