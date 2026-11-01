"""HTTP helpers with retries and robust charset detection."""
from __future__ import annotations

import re
import time
from typing import Any, List, Optional, Tuple

import requests

from .models import FetchIssue


def http_get(
    url: str,
    *,
    provider: str,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
) -> Tuple[Optional[requests.Response], List[FetchIssue]]:
    issues: List[FetchIssue] = []
    attempts = max_retries + 1

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                timeout=timeout_seconds,
                headers={"User-Agent": "job-finder-skill/1.2"},
            )
        except requests.RequestException as exc:
            retryable = attempt < attempts
            issues.append(FetchIssue(
                provider=provider,
                source_ref=url,
                message=f"Network error on attempt {attempt}/{attempts}: {exc}",
                severity="error" if not retryable else "warning",
                retryable=retryable,
                details={"attempt": attempt, "attempts": attempts},
            ))
            if retryable:
                time.sleep(retry_backoff_seconds)
                continue
            return None, issues

        if response.status_code >= 500 and attempt < attempts:
            issues.append(FetchIssue(
                provider=provider,
                source_ref=url,
                message=f"HTTP {response.status_code} on attempt {attempt}/{attempts}",
                severity="warning",
                retryable=True,
                details={"attempt": attempt, "attempts": attempts},
            ))
            time.sleep(retry_backoff_seconds)
            continue

        return response, issues

    return None, issues


def safe_get_json(
    url: str,
    *,
    provider: str,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
) -> tuple[Optional[Any], List[FetchIssue]]:
    response, issues = http_get(
        url,
        provider=provider,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    if response is None:
        return None, issues

    if response.status_code >= 400:
        issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=f"HTTP {response.status_code}",
            severity="error" if response.status_code >= 500 else "warning",
            retryable=response.status_code >= 500,
        ))
        return None, issues

    try:
        return response.json(), issues
    except ValueError:
        issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message="Response was not valid JSON",
            severity="error",
            retryable=False,
        ))
        return None, issues


def safe_get_text(
    url: str,
    *,
    provider: str,
    timeout_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
) -> tuple[Optional[str], List[FetchIssue]]:
    response, issues = http_get(
        url,
        provider=provider,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    if response is None:
        return None, issues

    if response.status_code >= 400:
        issues.append(FetchIssue(
            provider=provider,
            source_ref=url,
            message=f"HTTP {response.status_code}",
            severity="error" if response.status_code >= 500 else "warning",
            retryable=response.status_code >= 500,
        ))
        return None, issues

    # Detect encoding robustly — requests defaults to ISO-8859-1 for text/html
    # which breaks Japanese (UTF-8) pages.  Priority:
    #   1. charset declared in Content-Type header
    #   2. charset declared in <meta> tag
    #   3. UTF-8 (safe fallback for most modern pages)
    content_type = response.headers.get("content-type", "")
    ct_charset = re.search(r'charset=([^\s;]+)', content_type, re.I)
    if ct_charset:
        encoding = ct_charset.group(1).strip()
    else:
        raw = response.content
        meta_charset = re.search(
            rb'<meta[^>]+charset=["\']?([a-zA-Z0-9_\-]+)',
            raw[:4096], re.I,
        )
        encoding = meta_charset.group(1).decode("ascii") if meta_charset else "utf-8"

    try:
        return response.content.decode(encoding, errors="replace"), issues
    except (LookupError, UnicodeDecodeError):
        return response.content.decode("utf-8", errors="replace"), issues
