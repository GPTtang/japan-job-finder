"""GaijinPot Jobs aggregator."""
from __future__ import annotations

from typing import Any, Dict

from .extract import scan_for_jobs
from .http import safe_get_json
from .models import FetchResult
from .spa import spa_fetch_with_browser_fallback


def fetch_gaijinpot(fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch jobs from GaijinPot Jobs (jobs.gaijinpot.com).

    GaijinPot targets foreign workers in Japan with JLPT N2/N3 roles —
    a strong source for Chinese speakers in transition.
    Attempts static extraction first, then headless browser fallback.
    """
    fetch_options = fetch_options or {}
    provider = "gaijinpot"
    base_url = "https://jobs.gaijinpot.com"

    # Try the JSON search endpoint first (occasionally returns structured data)
    data, issues = safe_get_json(
        f"{base_url}/job/index/search",
        provider=provider,
        timeout_seconds=fetch_options.get("timeout_seconds", 15),
        max_retries=fetch_options.get("max_retries", 1),
        retry_backoff_seconds=fetch_options.get("retry_backoff_seconds", 0.5),
    )
    if data:
        jobs = scan_for_jobs(data, base_url, provider)
        if jobs:
            return FetchResult(provider=provider, jobs=jobs, issues=issues)

    return spa_fetch_with_browser_fallback(
        base_url,
        provider=provider,
        fetch_options=fetch_options,
        spa_hint="Django + client-side JS",
    )
