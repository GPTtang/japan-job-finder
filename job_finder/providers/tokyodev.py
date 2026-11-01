"""TokyoDev aggregator."""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .browser import playwright_get_text
from .models import FetchResult, make_job
from .spa import spa_fetch_with_browser_fallback
from .text import extract_basic_skills


def fetch_tokyodev(fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch jobs from TokyoDev (tokyodev.com/jobs).

    TokyoDev is a Rails application.  Job listings are embedded as
    /companies/{company-slug}/jobs/{job-slug} hrefs in the rendered HTML, so
    we extract them directly from those URL slugs — no JSON blob required.
    Falls back to spa_fetch_with_browser_fallback if the slug approach yields
    nothing (e.g. the site structure changes in the future).
    """
    fetch_options = fetch_options or {}
    provider = "tokyodev"
    base_url = "https://www.tokyodev.com"
    jobs_url = f"{base_url}/jobs"

    timeout_ms = int(fetch_options.get("browser_timeout_seconds", 30) * 1000)
    wait_until = fetch_options.get("browser_wait_until", "domcontentloaded")

    html, issues = playwright_get_text(jobs_url, timeout_ms=timeout_ms, wait_until=wait_until)
    result = FetchResult(provider=provider, issues=issues)

    if not html:
        return result

    # Extract jobs from /companies/{company-slug}/jobs/{job-slug} hrefs
    seen: set = set()
    jobs: List[Dict[str, Any]] = []
    for href, company_slug, job_slug in re.findall(
        r'href=["\'](/companies/([^/"\']+)/jobs/([^/"\'#?]+))["\']',
        html, re.I,
    ):
        key = (company_slug, job_slug)
        if key in seen:
            continue
        seen.add(key)
        company = company_slug.replace("-", " ").title()
        title   = job_slug.replace("-", " ").title()
        # Build full URL for the job detail page
        job_url = f"{base_url}{href}"
        # Infer description from title slug keywords + common context
        desc = f"{title} at {company}. English-friendly role in Tokyo, Japan."
        jobs.append(make_job(
            title=title,
            company=company,
            location="Tokyo, Japan",
            url=job_url,
            description=desc,
            source=provider,
            skills=extract_basic_skills(f"{title} {desc}"),
        ))

    if jobs:
        result.jobs = jobs
        return result

    # Fallback: generic SPA extraction
    return spa_fetch_with_browser_fallback(
        jobs_url,
        provider=provider,
        fetch_options=fetch_options,
        spa_hint="Rails/Hotwire SPA",
    )
