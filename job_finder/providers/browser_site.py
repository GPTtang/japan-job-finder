"""Career pages that only render in a browser (React/Vue/Next/Nuxt SPAs)."""
from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urljoin

from .browser import playwright_get_text
from .extract import extract_jobs_from_rendered_html
from .models import FetchIssue, FetchResult


def fetch_browser_site(url: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    """Fetch a careers page using headless Playwright — handles React/Vue/Next.js/Nuxt SPAs.

    Use this provider (``"browser_site"``) for any source whose static HTML is empty
    because the page is client-side rendered.  Falls back to a descriptive warning
    when Playwright is not installed so the rest of the pipeline is unaffected.
    """
    provider = "browser_site"
    fetch_options = fetch_options or {}
    timeout_ms = int(
        fetch_options.get("browser_timeout_seconds",
                          fetch_options.get("timeout_seconds", 30)) * 1000
    )
    wait_until = fetch_options.get("browser_wait_until", "networkidle")

    html, issues = playwright_get_text(url, timeout_ms=timeout_ms, wait_until=wait_until)
    result = FetchResult(provider=provider, issues=issues)

    if not html:
        return result

    jobs = extract_jobs_from_rendered_html(html, url, provider)

    if not jobs:
        # Follow career/recruit links found in the rendered page
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
        candidate_links: List[str] = []
        keywords = ("job", "jobs", "career", "careers", "recruit", "position",
                    "opening", "採用", "求人", "キャリア")
        for href in hrefs:
            if any(k in href.lower() for k in keywords):
                full = urljoin(url, href)
                if full != url and full not in candidate_links:
                    candidate_links.append(full)

        max_follow = fetch_options.get("max_follow_links", 3)
        for link in candidate_links[:max_follow]:
            child_html, child_issues = playwright_get_text(
                link, timeout_ms=timeout_ms, wait_until=wait_until,
            )
            result.issues.extend(child_issues)
            if child_html:
                jobs.extend(extract_jobs_from_rendered_html(child_html, link, provider))

    if not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=(
                "Browser rendered the page but found no structured job data. "
                "The site may use a fully custom listing format or require login."
            ),
            severity="warning",
            retryable=False,
        ))

    result.jobs = jobs
    return result
