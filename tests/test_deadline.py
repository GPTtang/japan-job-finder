import json

import pytest

from job_finder.dates import normalize_date
from job_finder.providers.extract import extract_json_ld_jobpostings
from job_finder.providers.models import make_job
from job_finder.rerank.merge import merge_reviews
from job_finder.rerank.packet import build_packet, job_key
from job_finder.rerank.profile import normalize_profile
from datetime import date


@pytest.mark.parametrize("value,expected", [
    ("2026-12-31", "2026-12-31"), ("2026-12-31T23:59:59+09:00", "2026-12-31"),
    ("2026-12-31T23:59:59Z", "2026-12-31"), ("2026-12-31 10:00", "2026-12-31"),
    ("2026-13-01", None), ("12/31/2026", None), ("", None), (None, None), (20261231, None), ("x" * 500, None),
])
def test_normalize_date(value, expected):
    assert normalize_date(value) == expected


def test_make_job_normalises_deadline():
    assert make_job(title="t", company="c", deadline="2026-12-31T00:00:00Z")["deadline"] == "2026-12-31"
    assert make_job(title="t", company="c", deadline="soon")["deadline"] is None
    assert make_job(title="t", company="c")["deadline"] is None


def _page(**extra):
    data = {"@type": "JobPosting", "title": "T", "hiringOrganization": {"name": "C"}, "description": "d", **extra}
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def test_json_ld_valid_through_becomes_deadline():
    jobs = extract_json_ld_jobpostings(_page(validThrough="2026-12-01T00:00"), "https://x/1")
    assert jobs[0]["deadline"] == "2026-12-01"


def test_json_ld_without_valid_through_has_no_deadline():
    assert extract_json_ld_jobpostings(_page(), "https://x/1")[0]["deadline"] is None


TODAY = date(2026, 11, 1)


def _merge(source_deadline, reviewer_deadline):
    job = {"title": "T", "company": "C", "url": "https://x/1", "description": "d", "match_score": 0.5,
           "deadline": source_deadline}
    profile = normalize_profile({"raw_query": "x"})
    review = {"key": job_key(job), "scores": {"technical": 80, "experience": 80, "language": 80, "career": 80},
              "deadline": reviewer_deadline}
    return merge_reviews(build_packet(profile, [job]), [review], today=TODAY)


def test_source_deadline_beats_reviewer_deadline():
    out = _merge("2026-11-03", "2027-01-01")
    assert out["ranked"][0]["deadline"] == "2026-11-03"
    assert any("🔥" in f for f in out["ranked"][0]["flags"])


def test_source_deadline_in_the_past_excludes_even_if_reviewer_says_open():
    assert _merge("2026-10-01", "2027-01-01")["excluded"]


def test_reviewer_deadline_used_when_source_has_none():
    assert _merge(None, "2026-11-04")["ranked"][0]["deadline"] == "2026-11-04"


def test_packet_carries_deadline_to_reviewers():
    from job_finder.rerank.batches import REVIEW_FIELDS
    assert "deadline" in REVIEW_FIELDS
    assert build_packet(normalize_profile({}), [{"title": "t", "deadline": "2026-11-04"}])["jobs"][0]["deadline"] == "2026-11-04"
