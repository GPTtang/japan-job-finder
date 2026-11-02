"""Lever ATS postings API."""
from __future__ import annotations

from typing import Any, Dict

from .http import safe_get_json
from .models import FetchIssue, FetchResult, make_job


def fetch_lever(company: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "lever"
    fetch_options = fetch_options or {}
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
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
    for item in data:
        categories = item.get("categories", {}) or {}
        location = categories.get("location", "") or ""
        lists = item.get("lists") or []
        list_text = lists[0].get("text", "") if lists else ""
        raw_desc = " ".join([
            item.get("descriptionPlain", "") or "",
            list_text,
        ])
        jobs.append(make_job(
            title=item.get("text", ""),
            company=company,
            location=location,
            url=item.get("hostedUrl", ""),
            description=raw_desc,
            source=provider,
            extract_skills=True,
            remote="remote" in location.lower(),
            posted_date=item.get("createdAt"),
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
