"""Ashby ATS job board API."""
from __future__ import annotations

from typing import Any, Dict

from .http import safe_get_json
from .models import FetchIssue, FetchResult, make_job


def fetch_ashby(board: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "ashby"
    fetch_options = fetch_options or {}
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
    data, issues = safe_get_json(
        url,
        provider=provider,
        timeout_seconds=fetch_options.get("timeout_seconds", 15),
        max_retries=fetch_options.get("max_retries", 1),
        retry_backoff_seconds=fetch_options.get("retry_backoff_seconds", 0.5),
    )
    result = FetchResult(provider=provider, issues=issues)

    if not data:
        return result

    jobs = []
    for item in data.get("jobs", []):
        desc = item.get("descriptionPlain", "") or item.get("descriptionHtml", "") or ""
        location = item.get("location", "") or ""
        jobs.append(make_job(
            title=item.get("title", ""),
            company=board,
            location=location,
            url=item.get("jobUrl", ""),
            description=desc,
            source=provider,
            extract_skills=True,
            remote="remote" in location.lower(),
            posted_date=item.get("publishedDate"),
        ))

    if not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="No jobs returned from source",
            severity="warning",
            retryable=False,
        ))
    result.jobs = jobs
    return result
