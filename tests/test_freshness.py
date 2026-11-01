from datetime import date

import pytest

from job_finder.rerank.freshness import freshness_flags
from job_finder.rerank.merge import merge_reviews
from job_finder.rerank.packet import build_packet, job_key
from job_finder.rerank.profile import normalize_profile
from job_finder.rerank.report import format_reviewed_report

TODAY = date(2026, 11, 1)


@pytest.mark.parametrize("posted,deadline,expired,flags", [
    (None, None, False, []),
    ("2026-10-25", None, False, []),
    ("2026-10-02", None, False, []),
    ("2026-10-01", None, False, ["发布于 31 天前，可能已过时"]),
    ("garbage", None, False, []),
    (None, "2026-11-08", False, ["🔥 距截止还有 7 天"]),
    (None, "2026-11-01", False, ["🔥 今天截止"]),
    (None, "2026-11-09", False, []),
    (None, "2026-10-31", True, []),
])
def test_freshness(posted, deadline, expired, flags):
    assert freshness_flags(posted, deadline, TODAY) == (expired, flags)


def _merged(posted, deadline):
    job = {"title": "T", "company": "C", "location": "Tokyo", "url": "https://x/1", "description": "d",
           "skills": [], "source": "s", "guard": "clean", "match_score": 0.5, "posted_date": posted}
    profile = normalize_profile({"raw_query": "x"})
    review = {"key": job_key(job), "scores": {"technical": 80, "experience": 80, "language": 80, "career": 80},
              "deadline": deadline}
    return profile, merge_reviews(build_packet(profile, [job]), [review], today=TODAY)


def test_merge_flags_stale_posting_but_keeps_it():
    _, out = _merged("2026-09-01", None)
    assert any("可能已过时" in f for f in out["ranked"][0]["flags"])


def test_merge_excludes_expired_deadline():
    _, out = _merged(None, "2026-10-01")
    assert out["ranked"] == [] and "已过截止日" in out["excluded"][0]["excluded_reasons"][0]


def test_report_shows_urgency():
    profile, out = _merged(None, "2026-11-05")
    assert "🔥" in format_reviewed_report(profile, out)
