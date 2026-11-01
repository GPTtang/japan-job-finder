"""Static company career pages: JSON-LD, linked career pages, then heuristics."""
from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urljoin

from .extract import extract_json_ld_jobpostings, extract_jobs_from_html_heuristic
from .http import safe_get_text
from .models import FetchIssue, FetchResult


def fetch_company_site(url: str, fetch_options: Dict[str, Any] | None = None) -> FetchResult:
    provider = "company_site"
    fetch_options = fetch_options or {}
    timeout = fetch_options.get("timeout_seconds", 15)
    retries = fetch_options.get("max_retries", 1)
    backoff = fetch_options.get("retry_backoff_seconds", 0.5)

    html, issues = safe_get_text(url, provider=provider,
                                   timeout_seconds=timeout, max_retries=retries,
                                   retry_backoff_seconds=backoff)
    result = FetchResult(provider=provider, issues=issues)
    if not html:
        return result

    # 1. JSON-LD structured data (best quality)
    jobs = extract_json_ld_jobpostings(html, url)
    if jobs:
        result.jobs = jobs
        return result

    # 2. Follow career/recruit links (Japanese: 採用, 求人; English: career/jobs)
    career_keywords = ("job", "jobs", "career", "careers", "recruit", "position",
                       "opening", "採用", "求人", "キャリア", "saiyou")
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    candidate_links: List[str] = []
    for href in hrefs:
        if any(k in href.lower() for k in career_keywords):
            full = urljoin(url, href)
            if full != url and full not in candidate_links:
                candidate_links.append(full)

    followed_htmls: List[tuple[str, str]] = []
    max_follow_links = fetch_options.get("max_follow_links", 3)
    for link in candidate_links[:max_follow_links]:
        child_html, child_issues = safe_get_text(link, provider=provider,
                                                   timeout_seconds=timeout,
                                                   max_retries=retries,
                                                   retry_backoff_seconds=backoff)
        result.issues.extend(child_issues)
        if not child_html:
            continue
        followed_htmls.append((child_html, link))
        child_jobs = extract_json_ld_jobpostings(child_html, link)
        jobs.extend(child_jobs)

    if jobs:
        result.jobs = jobs
        return result

    # 3. Heuristic extraction — plain HTML tables/lists (Japanese career pages)
    jobs = extract_jobs_from_html_heuristic(html, url)
    if not jobs:
        for child_html, child_url in followed_htmls:
            jobs = extract_jobs_from_html_heuristic(child_html, child_url)
            if jobs:
                break

    if not followed_htmls and not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="No career links found and heuristic extraction yielded nothing",
            severity="warning",
            retryable=False,
        ))
    elif not jobs:
        result.issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="Careers page found but no jobs extracted (JSON-LD or heuristic)",
            severity="warning",
            retryable=False,
            details={"followed_links": len(followed_htmls)},
        ))

    result.jobs = jobs
    return result
