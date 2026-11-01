"""japan-dev.com aggregator."""
from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, List

from .browser import playwright_get_text
from .models import FetchResult, make_job
from .spa import spa_fetch_with_browser_fallback
from .text import extract_basic_skills


def fetch_japan_dev(fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch jobs from japan-dev.com (Nuxt/Algolia SPA).

    The rendered HTML contains job titles in <h2><a class="job-item__title">
    and company names in a parent element's data attribute.  We parse these
    directly from the rendered DOM rather than looking for JSON blobs.
    """
    fetch_options = fetch_options or {}
    provider = "japan_dev"
    base_url = "https://japan-dev.com"
    jobs_url = f"{base_url}/jobs"

    timeout_ms = int(fetch_options.get("browser_timeout_seconds", 30) * 1000)
    wait_until = fetch_options.get("browser_wait_until", "domcontentloaded")

    html, issues = playwright_get_text(jobs_url, timeout_ms=timeout_ms, wait_until=wait_until)
    result = FetchResult(provider=provider, issues=issues)

    if not html:
        return result

    jobs: List[Dict[str, Any]] = []

    # Pattern: <h2><a href="/jobs/{company}/{slug}" class="job-item__title">TITLE</a></h2>
    # Company name sits in a parent element: data-...="COMPANY"  or in .job-item__contract-type
    for m in re.finditer(
        r'<h2[^>]*>\s*<a\s+href=["\'](/jobs/([^/"\']+)/[^"\']+)["\'][^>]*class=["\'][^"\']*job-item__title[^"\']*["\'][^>]*>(.*?)</a>\s*</h2>',
        html, re.I | re.S,
    ):
        href, company_slug, raw_title = m.group(1), m.group(2), m.group(3)
        title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        company = company_slug.replace("-", " ").title()

        # Grab nearby text for description (up to 400 chars after the heading)
        pos = m.end()
        nearby = unescape(re.sub(r"<[^>]+>", " ", html[pos: pos + 600])).strip()[:300]

        jobs.append(make_job(
            title=title,
            company=company,
            location="Japan (Tokyo / Remote)",
            url=f"{base_url}{href}",
            description=nearby,
            source=provider,
            skills=extract_basic_skills(f"{title} {nearby}"),
        ))

    if jobs:
        result.jobs = jobs
        return result

    # Fallback: generic SPA extraction
    return spa_fetch_with_browser_fallback(
        jobs_url, provider=provider, fetch_options=fetch_options,
        spa_hint="Nuxt/Algolia SPA",
    )
