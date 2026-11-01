"""Fakes for the network and the headless browser, independent of module layout."""
from __future__ import annotations

import json
import sys
import types
from typing import Any, Callable, Dict, List, Optional, Union

import requests


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        *,
        json_data: Any = None,
        text: str = "",
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_data
        self.content = text.encode("utf-8") if text else b""
        self.headers = headers or {}

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("not json")
        return self._json


class CallLog(list):
    """List of requested URLs that also keeps the keyword arguments of each call."""

    def __init__(self) -> None:
        super().__init__()
        self.kwargs: List[Dict[str, Any]] = []


Route = Union[FakeResponse, Exception, Callable[[], Union[FakeResponse, Exception]]]


def install_requests(monkeypatch, routes: Dict[str, Route]) -> CallLog:
    """Route ``requests.get`` by URL substring; returns the list of requested URLs.

    A route may be a response, an exception to raise, or a callable producing either
    (to script a different answer per attempt). Unrouted URLs answer 404.
    """
    calls = CallLog()

    def fake_get(url, **kwargs):
        calls.append(url)
        calls.kwargs.append(kwargs)
        for fragment, route in routes.items():
            if fragment in url:
                outcome = route() if callable(route) else route
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        return FakeResponse(404)

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    return calls


def install_playwright(monkeypatch, pages: Dict[str, str]) -> List[str]:
    """Provide a fake ``playwright.sync_api``; returns the list of navigated URLs."""
    visited: List[str] = []

    class Page:
        def __init__(self) -> None:
            self._html = ""

        def goto(self, url, **kwargs):
            visited.append(url)
            if url not in pages:
                raise RuntimeError(f"navigation failed: {url}")
            self._html = pages[url]

        def content(self) -> str:
            return self._html

    class Context:
        def new_page(self) -> Page:
            return Page()

    class Browser:
        def new_context(self, **kwargs) -> Context:
            return Context()

        def close(self) -> None:
            pass

    class Chromium:
        def launch(self, **kwargs) -> Browser:
            return Browser()

    class Manager:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    package = types.ModuleType("playwright")
    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = lambda: Manager()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    return visited


def uninstall_playwright(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)


def json_ld_page(title="Backend Engineer", org="Acme", description="<p>Python and FastAPI</p>") -> str:
    data = {
        "@type": "JobPosting",
        "title": title,
        "hiringOrganization": {"name": org},
        "jobLocation": {"address": {"addressLocality": "Tokyo"}},
        "description": description,
        "datePosted": "2026-10-01",
    }
    return f'<html><script type="application/ld+json">{json.dumps(data)}</script></html>'
