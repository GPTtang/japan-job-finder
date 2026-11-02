"""Headless-browser fetch (optional dependency: playwright)."""
from __future__ import annotations

from typing import List, Optional

from .models import FetchIssue


def playwright_get_text(
    url: str,
    *,
    timeout_ms: int = 30_000,
    wait_until: str = "networkidle",
) -> tuple[Optional[str], List["FetchIssue"]]:
    """Fetch ``url`` with a headless Chromium browser and return the rendered HTML.

    Returns ``(None, issues)`` if Playwright is not installed or the fetch fails,
    so callers can degrade gracefully without crashing.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import]
    except ImportError:
        return None, [FetchIssue(
            provider="browser",
            source_ref=url,
            message=(
                "Playwright not installed — JS rendering unavailable. "
                "To enable: pip install playwright && playwright install chromium"
            ),
            severity="warning",
            retryable=False,
        )]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="ja-JP",
            )
            page = ctx.new_page()
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            html = page.content()
            browser.close()
            return html, []
    except Exception as exc:  # noqa: BLE001
        return None, [FetchIssue(
            provider="browser",
            source_ref=url,
            message=f"Playwright error: {exc}",
            severity="error",
            retryable=False,
        )]
