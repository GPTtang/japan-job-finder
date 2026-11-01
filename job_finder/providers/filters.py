"""Provider-level keyword/location/remote filters."""
from __future__ import annotations

from typing import Any, Dict, List

from .models import FetchIssue
from .text import job_text


def apply_source_filters(
    jobs: List[Dict[str, Any]],
    filters: Dict[str, Any] | None,
    provider: str,
) -> tuple[List[Dict[str, Any]], List[FetchIssue]]:
    if not filters:
        return jobs, []

    issues: List[FetchIssue] = []
    filtered = jobs

    keywords = filters.get("keywords") or []
    if keywords:
        keywords_l = [k.lower() for k in keywords]
        filtered = [
            job for job in filtered
            if any(k in job_text(job) for k in keywords_l)
        ]

    locations = filters.get("locations") or []
    if locations:
        locations_l = [loc.lower() for loc in locations]
        filtered = [
            job for job in filtered
            if not str(job.get("location", "")).strip()  # no location set → keep
            or any(loc in str(job.get("location", "")).lower() for loc in locations_l)
        ]

    if filters.get("remote_only"):
        filtered = [job for job in filtered if job.get("remote") is True]
    elif filters.get("remote_preferred"):
        remote_jobs = [job for job in filtered if job.get("remote") is True]
        non_remote_jobs = [job for job in filtered if job.get("remote") is not True]
        filtered = remote_jobs + non_remote_jobs

    if not filtered and jobs:
        issues.append(FetchIssue(
            provider=provider,
            message="Provider-level filters removed all fetched jobs",
            severity="warning",
            retryable=False,
            details={"filters": filters, "original_count": len(jobs)},
        ))

    return filtered, issues
