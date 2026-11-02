"""Result types and the job record every provider produces."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..dates import normalize_date
from ..guard import GuardResult, guard, guard_plain
from .text import extract_basic_skills


@dataclass
class FetchIssue:
    provider: str
    message: str
    source_ref: str = ""
    severity: str = "warning"
    retryable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    provider: str
    jobs: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[FetchIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the fetch completed without any error-severity issues.

        An empty ``jobs`` list is *not* a failure — the source may simply have
        no open positions right now.  Callers that care about emptiness should
        check ``len(result.jobs) > 0`` separately.
        """
        return not any(i.severity == "error" for i in self.issues)


def make_job(
    *,
    title: str,
    company: str,
    location: str = "",
    url: str = "",
    description: str = "",
    source: str = "",
    skills: Optional[List[str]] = None,
    extract_skills: bool = False,
    remote: Optional[bool] = None,
    posted_date: Optional[str] = None,
    deadline: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a job record.

    ``description`` may be raw HTML or text from an untrusted source: it passes
    through the integrity gate, which stores the cleaned text and a verdict in
    ``guard``. Title, company and location are gated as plain text and their
    findings join the same verdict. With ``extract_skills`` the skill list is read from that cleaned
    text, so hidden keyword stuffing cannot inflate the match.
    """
    checked = guard(description)
    short = {
        "title": guard_plain(title, "title"),
        "company": guard_plain(company, "company"),
        "location": guard_plain(location, "location"),
    }
    if skills is None and extract_skills:
        skills = extract_basic_skills(checked.text)
    findings = checked.findings + tuple(f for r in short.values() for f in r.findings)
    return {
        "title": short["title"].text,
        "company": short["company"].text,
        "location": short["location"].text,
        "url": url or "",
        "description": checked.text,
        "source": source or "",
        "skills": skills or [],
        "remote": remote,
        "posted_date": posted_date,
        "deadline": normalize_date(deadline),
        "guard": GuardResult(text="", findings=findings).verdict,
    }
