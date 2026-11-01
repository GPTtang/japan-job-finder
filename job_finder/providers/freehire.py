"""freehire.me: tech jobs from ~50 ATS platforms through one public JSON API.

Reads are unauthenticated. The service is a third-party, best-effort host, so every
failure degrades to an issue instead of an exception, and the base URL can be pointed
at a self-hosted instance with ``FREEHIRE_API_URL``. Everything in a response is
untrusted: fields are type-checked and bounded, and descriptions go through the
integrity gate in ``make_job``.
"""
from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlencode, urlparse

from .http import safe_get_json
from .models import FetchIssue, FetchResult, make_job

PROVIDER = "freehire"
DEFAULT_BASE_URL = "https://freehire.me"
BASE_URL_ENV = "FREEHIRE_API_URL"
SEARCH_PATH = "/api/v1/agent/jobs/search"

DEFAULT_COUNTRIES = ("JP",)
DEFAULT_LIMIT = 30
MAX_PAGE_SIZE = 100  # the API clamps larger values
MAX_PAGES = 3
MAX_QUERY_ALTERNATIVES = 5  # the API rejects a sixth OR alternative
WORK_MODES = ("remote", "hybrid", "onsite")
OPTIONAL_FIELDS = (
    "query", "countries", "limit", "pages", "posted_within_days",
    "work_mode", "category", "seniority",
)

_MAX_TITLE, _MAX_NAME, _MAX_SKILL, _MAX_SKILLS = 200, 120, 40, 30
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_COUNTRY = re.compile(r"^[A-Za-z]{2}$")


def _text(value: Any, cap: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(value).split())[:cap]


def _in_range(value: Any, default: int, low: int, high: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
        return value
    return default


def _str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def resolve_base_url() -> Tuple[Optional[str], Optional[str]]:
    """Return ``(base_url, problem)``; only http(s) URLs are accepted."""
    raw = os.environ.get(BASE_URL_ENV, "").strip()
    if not raw:
        return DEFAULT_BASE_URL, None
    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return raw.rstrip("/"), None
    return None, f"{BASE_URL_ENV} must be an http(s) URL, got {raw[:60]!r}"


def build_query(source: Mapping[str, Any]) -> str:
    explicit = source.get("query")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    keywords = (source.get("filters") or {}).get("keywords") or []
    picked: List[str] = []
    seen = set()
    for keyword in keywords:
        if not isinstance(keyword, str):
            continue
        # A double quote would change how the API parses the query; a bare OR is its operator.
        words = [w for w in keyword.replace('"', " ").split() if w != "OR"]
        cleaned = " ".join(words)
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            picked.append(cleaned)
        if len(picked) == MAX_QUERY_ALTERNATIVES:
            break
    return " OR ".join(picked)


def build_params(source: Mapping[str, Any], limit: int, offset: int) -> List[Tuple[str, str]]:
    params: List[Tuple[str, str]] = [
        ("limit", str(limit)), ("offset", str(offset)), ("description_format", "text"),
    ]
    query = build_query(source)
    if query:
        params.append(("q", query))
    for country in _str_list(source.get("countries")) or list(DEFAULT_COUNTRIES):
        params.append(("countries", country))
    for facet in ("category", "seniority"):
        params.extend((facet, value) for value in _str_list(source.get(facet)))
    days = _in_range(source.get("posted_within_days"), 0, 1, 3650)
    if days:
        params.append(("posted_within_days", str(days)))
    if source.get("work_mode") in WORK_MODES:
        params.append(("work_mode", source["work_mode"]))
    return params


def _location(item: Mapping[str, Any]) -> str:
    location = _text(item.get("location"), _MAX_NAME)
    if location:
        return location
    cities, countries = _str_list(item.get("cities")), _str_list(item.get("countries"))
    parts = [cities[0] if cities else "", countries[0].upper() if countries else ""]
    return ", ".join(p for p in parts if p)


def _remote(work_mode: Any) -> Optional[bool]:
    if work_mode == "remote":
        return True
    return False if work_mode in ("hybrid", "onsite") else None


def _merge_skills(extracted: List[str], reported: List[str]) -> List[str]:
    seen = {s.lower() for s in extracted}
    extra = [s for s in reported if s.lower() not in seen]
    return (extracted + extra)[:_MAX_SKILLS]


def parse_job(item: Any) -> Optional[Dict[str, Any]]:
    """Turn one API record into a job, or ``None`` if it is malformed or closed."""
    if not isinstance(item, dict) or item.get("closed_at"):
        return None
    url = item.get("url")
    posted = next((m.group() for m in (_DATE.match(str(item.get(k) or ""))
                                       for k in ("posted_at", "created_at")) if m), None)
    reported = [s[:_MAX_SKILL] for s in _str_list(item.get("skills"))][:_MAX_SKILLS]
    job = make_job(
        title=_text(item.get("title"), _MAX_TITLE) or "(untitled)",
        company=_text(item.get("company"), _MAX_NAME) or _text(item.get("company_slug"), _MAX_NAME),
        location=_location(item),
        url=url if isinstance(url, str) and url.startswith(("http://", "https://")) else "",
        description=item.get("description") if isinstance(item.get("description"), str) else "",
        source=PROVIDER,
        extract_skills=True,
        remote=_remote(item.get("work_mode")),
        posted_date=posted,
    )
    return {**job, "skills": _merge_skills(job["skills"], reported)}


def _issue(message: str, url: str, severity: str = "warning") -> FetchIssue:
    return FetchIssue(provider=PROVIDER, source_ref=url, message=message, severity=severity)


def _page_is_last(count: int, limit: int, offset: int, data: Mapping[str, Any]) -> bool:
    meta = data.get("meta")
    total = meta.get("total") if isinstance(meta, dict) else None
    reached_total = isinstance(total, int) and offset + count >= total
    return count < limit or reached_total


def fetch_freehire(source: Mapping[str, Any], fetch_options: Optional[Dict[str, Any]] = None) -> FetchResult:
    options = fetch_options or {}
    base_url, problem = resolve_base_url()
    if base_url is None:
        return FetchResult(provider=PROVIDER, issues=[_issue(problem or "Invalid base URL", "", "error")])

    limit = _in_range(source.get("limit"), DEFAULT_LIMIT, 1, MAX_PAGE_SIZE)
    pages = _in_range(source.get("pages"), 1, 1, MAX_PAGES)
    result = FetchResult(provider=PROVIDER)
    jobs: List[Dict[str, Any]] = []
    seen_keys = set()
    skipped = 0
    url = base_url + SEARCH_PATH

    for page in range(pages):
        offset = page * limit
        url = f"{base_url}{SEARCH_PATH}?{urlencode(build_params(source, limit, offset))}"
        data, issues = safe_get_json(
            url,
            provider=PROVIDER,
            timeout_seconds=options.get("timeout_seconds", 15),
            max_retries=options.get("max_retries", 1),
            retry_backoff_seconds=options.get("retry_backoff_seconds", 0.5),
        )
        result.issues.extend(issues)
        if data is None:
            break
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            result.issues.append(_issue("Unexpected response shape from freehire", url, "error"))
            break

        records = data["data"]
        for record in records:
            job = parse_job(record)
            if job is None:
                skipped += 0 if isinstance(record, dict) else 1
                continue
            key = job["url"] or record.get("public_slug")
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            jobs.append(job)
        if _page_is_last(len(records), limit, offset, data):
            break

    if skipped:
        result.issues.append(_issue(f"Skipped {skipped} malformed postings", url))
    if not jobs and not result.issues:
        result.issues.append(_issue("No jobs returned from source", url))
    result.jobs = jobs
    return result


def validate_source(source: Mapping[str, Any]) -> List[Tuple[str, str]]:
    """Return ``(field, problem)`` pairs for invalid freehire settings."""
    problems: List[Tuple[str, str]] = []

    def check(field: str, ok: bool, message: str) -> None:
        if field in source and not ok:
            problems.append((field, message))

    def int_between(value: Any, low: int, high: int) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high

    countries = source.get("countries")
    check("query", isinstance(source.get("query"), str), "必须是字符串。")
    check("countries", isinstance(countries, list) and bool(countries)
          and all(isinstance(c, str) and _COUNTRY.match(c) for c in countries),
          "必须是非空的两位国家代码数组，例如 [\"JP\"]。")
    for field in ("category", "seniority"):
        value = source.get(field)
        check(field, isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value),
              "必须是非空字符串数组。")
    check("limit", int_between(source.get("limit"), 1, MAX_PAGE_SIZE), f"必须是 1 到 {MAX_PAGE_SIZE} 的整数。")
    check("pages", int_between(source.get("pages"), 1, MAX_PAGES), f"必须是 1 到 {MAX_PAGES} 的整数。")
    check("posted_within_days", int_between(source.get("posted_within_days"), 1, 3650), "必须是正整数。")
    check("work_mode", source.get("work_mode") in WORK_MODES, f"必须是 {'/'.join(WORK_MODES)} 之一。")
    return problems
