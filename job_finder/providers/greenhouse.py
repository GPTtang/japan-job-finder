"""Greenhouse ATS job board API."""
from __future__ import annotations

from typing import Any, Dict

from .http import safe_get_json
from .models import FetchIssue, FetchResult, make_job


def fetch_greenhouse(token: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "greenhouse"
    fetch_options = fetch_options or {}
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
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
        content = item.get("content", "") or ""
        location_name = (item.get("location") or {}).get("name", "")
        jobs.append(make_job(
            title=item.get("title", ""),
            company=token,
            location=location_name,
            url=item.get("absolute_url", ""),
            description=content,
            source=provider,
            extract_skills=True,
            remote="remote" in location_name.lower(),
            posted_date=item.get("updated_at") or item.get("created_at"),
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
