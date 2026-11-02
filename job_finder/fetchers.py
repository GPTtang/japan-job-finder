"""Compatibility facade: the implementation lives in :mod:`job_finder.providers`."""
from __future__ import annotations

from .providers import (
    FetchIssue,
    FetchResult,
    fetch_all,
    fetch_from_source,
    make_job,
    seed_jobs,
)
from .providers.ashby import fetch_ashby
from .providers.browser_site import fetch_browser_site
from .providers.company_site import fetch_company_site
from .providers.gaijinpot import fetch_gaijinpot
from .providers.greenhouse import fetch_greenhouse
from .providers.japan_dev import fetch_japan_dev
from .providers.lever import fetch_lever
from .providers.tokyodev import fetch_tokyodev

__all__ = [
    "FetchIssue", "FetchResult", "fetch_all", "fetch_from_source", "make_job", "seed_jobs",
    "fetch_ashby", "fetch_browser_site", "fetch_company_site", "fetch_gaijinpot",
    "fetch_greenhouse", "fetch_japan_dev", "fetch_lever", "fetch_tokyodev",
]
