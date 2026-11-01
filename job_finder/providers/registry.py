"""Provider table and the entry points that fetch from configured sources."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from types import MappingProxyType
from typing import Any, Callable, Dict, Iterable, List, Mapping, NamedTuple, Optional, Tuple

from .ashby import fetch_ashby
from .browser_site import fetch_browser_site
from .company_site import fetch_company_site
from .filters import apply_source_filters
from .gaijinpot import fetch_gaijinpot
from .greenhouse import fetch_greenhouse
from .japan_dev import fetch_japan_dev
from .lever import fetch_lever
from .models import FetchIssue, FetchResult
from .tokyodev import fetch_tokyodev

FetchOptions = Optional[Dict[str, Any]]


class Provider(NamedTuple):
    """A job source: the config fields it needs and how to fetch from it."""

    required: Tuple[str, ...]
    fetch: Callable[[Mapping[str, Any], FetchOptions], FetchResult]


PROVIDERS: Mapping[str, Provider] = MappingProxyType({
    "greenhouse": Provider(("token",), lambda s, o: fetch_greenhouse(s["token"], fetch_options=o)),
    "lever": Provider(("company",), lambda s, o: fetch_lever(s["company"], fetch_options=o)),
    "ashby": Provider(("board",), lambda s, o: fetch_ashby(s["board"], fetch_options=o)),
    # Static HTML fetch + JSON-LD extraction (fast, no browser required)
    "company_site": Provider(("url",), lambda s, o: fetch_company_site(s["url"], fetch_options=o)),
    # Headless Playwright fetch, for SPA/React/Vue/Next.js/Nuxt career pages.
    # Requires: pip install playwright && playwright install chromium
    "browser_site": Provider(("url",), lambda s, o: fetch_browser_site(s["url"], fetch_options=o)),
    # Built-in aggregators (static fetch + automatic browser fallback)
    "japan_dev": Provider((), lambda s, o: fetch_japan_dev(fetch_options=o)),
    "gaijinpot": Provider((), lambda s, o: fetch_gaijinpot(fetch_options=o)),
    "tokyodev": Provider((), lambda s, o: fetch_tokyodev(fetch_options=o)),
})


def fetch_from_source(source: Dict[str, Any], fetch_options: FetchOptions = None) -> FetchResult:
    name = source.get("provider")
    provider = PROVIDERS.get(name) if isinstance(name, str) else None
    if provider is None:
        label = str(name or "unknown")
        return FetchResult(
            provider=label,
            issues=[
                FetchIssue(
                    provider=label,
                    message="Unsupported provider in source config",
                    severity="error",
                    retryable=False,
                    details={"source": source},
                )
            ],
        )

    result = provider.fetch(source, fetch_options)
    filtered_jobs, filter_issues = apply_source_filters(
        result.jobs, source.get("filters"), provider=str(name),
    )
    result.jobs = filtered_jobs
    result.issues.extend(filter_issues)
    return result


def fetch_all(sources: Iterable[Dict[str, Any]], fetch_options: Dict[str, Any] | None = None) -> Dict[str, Any]:
    fetch_options = fetch_options or {}

    active_sources: List[Dict[str, Any]] = []
    for source in sources:
        if isinstance(source, dict) and source and all(k.startswith("_") for k in source.keys()):
            continue
        active_sources.append(source)

    if not active_sources:
        return {"jobs": [], "issues": []}

    all_jobs: List[Dict[str, Any]] = []
    all_issues: List[Dict[str, Any]] = []

    max_workers = fetch_options.get("max_concurrent_fetches")
    if not isinstance(max_workers, int) or max_workers <= 0:
        max_workers = min(4, len(active_sources)) or 1

    def _collect(result: FetchResult) -> None:
        all_jobs.extend(result.jobs)
        all_issues.extend([
            {
                "provider": issue.provider,
                "message": issue.message,
                "source_ref": issue.source_ref,
                "severity": issue.severity,
                "retryable": issue.retryable,
                "details": issue.details,
            }
            for issue in result.issues
        ])

    def _safe_fetch(source: Dict[str, Any]) -> FetchResult:
        try:
            return fetch_from_source(source, fetch_options=fetch_options)
        except Exception as exc:  # noqa: BLE001
            provider = "unknown"
            if isinstance(source, dict):
                provider = str(source.get("provider") or "unknown")
            return FetchResult(
                provider=provider,
                issues=[
                    FetchIssue(
                        provider=provider,
                        message=f"未处理的抓取异常：{exc}",
                        severity="error",
                        retryable=False,
                        details={"source": source},
                    )
                ],
            )

    if max_workers == 1:
        for source in active_sources:
            _collect(_safe_fetch(source))
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_safe_fetch, source): source for source in active_sources}
            for future in as_completed(future_map):
                _collect(future.result())

    return {
        "jobs": all_jobs,
        "issues": all_issues,
    }
