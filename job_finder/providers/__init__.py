"""Job source providers and the registry that dispatches to them."""
from __future__ import annotations

from .models import FetchIssue, FetchResult, make_job
from .registry import PROVIDERS, Provider, fetch_all, fetch_from_source
from .seed import seed_jobs

__all__ = [
    "FetchIssue", "FetchResult", "make_job",
    "PROVIDERS", "Provider", "fetch_all", "fetch_from_source", "seed_jobs",
]
