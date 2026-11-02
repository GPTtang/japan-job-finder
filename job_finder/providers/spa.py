"""Static fetch with a headless-browser fallback, for JS-rendered listing pages."""
from __future__ import annotations

from typing import Any, Dict, List

from .browser import playwright_get_text
from .extract import extract_jobs_from_rendered_html
from .http import safe_get_text
from .models import FetchIssue, FetchResult


def spa_fetch_with_browser_fallback(
    url: str,
    provider: str,
    fetch_options: Dict[str, Any],
    spa_hint: str = "",
) -> FetchResult:
    """Shared helper: static fetch → extract → browser fallback if empty.

    1. Fetch static HTML via requests.
    2. Run extract_jobs_from_rendered_html (covers JSON-LD, Next/Nuxt blobs, etc.).
    3. If still empty and Playwright is available, retry with headless browser.
    """
    timeout = fetch_options.get("timeout_seconds", 15)
    retries = fetch_options.get("max_retries", 1)
    backoff = fetch_options.get("retry_backoff_seconds", 0.5)

    html, issues = safe_get_text(
        url, provider=provider,
        timeout_seconds=timeout, max_retries=retries, retry_backoff_seconds=backoff,
    )
    result = FetchResult(provider=provider, issues=issues)

    jobs: List[Dict[str, Any]] = []
    if html:
        jobs = extract_jobs_from_rendered_html(html, url, provider)

    if not jobs:
        # Attempt headless browser fallback
        timeout_ms = int(fetch_options.get("browser_timeout_seconds", 30) * 1000)
        wait_until = fetch_options.get("browser_wait_until", "networkidle")
        browser_html, browser_issues = playwright_get_text(
            url, timeout_ms=timeout_ms, wait_until=wait_until,
        )
        # Only surface Playwright issues when the static fetch also yielded nothing
        result.issues.extend(browser_issues)
        if browser_html:
            jobs = extract_jobs_from_rendered_html(browser_html, url, provider)

    if not jobs:
        hint = f" ({spa_hint})" if spa_hint else ""
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=(
                f"{provider}{hint}: no job data found in static HTML or browser render. "
                "The site may be fully JS-rendered with Algolia/custom APIs — "
                "consider adding it as a 'browser_site' source with specific subpages."
            ),
            severity="warning",
            retryable=False,
        ))

    result.jobs = jobs
    return result
