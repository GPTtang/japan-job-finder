import json

import pytest

from job_finder.rerank.packet import (
    PACKET_VERSION,
    REVIEW_SCHEMA,
    build_packet,
    job_key,
    report_language,
)
from job_finder.rerank.profile import normalize_profile

PROFILE = normalize_profile({"raw_query": "Backend Engineer in Tokyo", "skills": ["Python"]})


def job(**overrides):
    base = {
        "title": "Backend Engineer", "company": "Acme", "location": "Tokyo", "url": "https://a.example/1",
        "description": "Build APIs.", "skills": ["Python"], "source": "freehire", "remote": None,
        "posted_date": "2026-10-01", "guard": "clean", "match_score": 0.8, "gaps": ["AWS"],
        "fit_reasons": ["技能命中：Python"],
    }
    return {**base, **overrides}


class TestJobKey:
    def test_stable_and_short(self):
        assert job_key(job()) == job_key(job()) and len(job_key(job())) == 10

    def test_differs_by_url_title_and_company(self):
        keys = {job_key(job()), job_key(job(url="https://a.example/2")),
                job_key(job(title="Other")), job_key(job(company="B"))}
        assert len(keys) == 4

    def test_tolerates_missing_fields(self):
        assert job_key({}) == job_key({"title": "", "company": "", "url": ""})


class TestReportLanguage:
    @pytest.mark.parametrize("query,expected", [
        ("东京的后端工程师", "中文"), ("バックエンドエンジニア募集", "日本語"),
        ("backend engineer in Tokyo", "English"), ("", "中文"),
    ])
    def test_detects_from_the_query(self, query, expected):
        assert report_language({"raw_query": query}) == expected


class TestBuildPacket:
    def test_shape(self):
        packet = build_packet(PROFILE, [job()])
        assert packet["version"] == PACKET_VERSION and packet["profile"] == PROFILE
        assert "technical" in packet["rubric"] and packet["schema"] == REVIEW_SCHEMA
        assert packet["report_language"] == "English"

    def test_job_fields_and_key(self):
        entry = build_packet(PROFILE, [job()])["jobs"][0]
        assert entry["key"] == job_key(job())
        assert entry["rule_score"] == 0.8 and entry["guard"] == "clean"
        assert entry["description"] == "Build APIs." and entry["description_truncated"] is False
        assert {"title", "company", "location", "url", "source", "posted_date", "skills", "remote"} <= entry.keys()

    def test_long_descriptions_are_truncated_and_marked(self):
        entry = build_packet(PROFILE, [job(description="x" * 5000)], max_description_chars=100)["jobs"][0]
        assert len(entry["description"]) == 100 and entry["description_truncated"] is True

    def test_order_is_preserved(self):
        titles = ["A", "B", "C"]
        packet = build_packet(PROFILE, [job(title=t, url=f"https://x/{t}") for t in titles])
        assert [j["title"] for j in packet["jobs"]] == titles

    def test_duplicate_postings_collapse_to_one_entry(self):
        assert len(build_packet(PROFILE, [job(), job()])["jobs"]) == 1

    def test_inputs_are_not_mutated(self):
        jobs = [job()]
        snapshot = json.loads(json.dumps(jobs))
        build_packet(PROFILE, jobs)
        assert jobs == snapshot

    def test_is_json_serialisable(self):
        json.dumps(build_packet(PROFILE, [job()]), ensure_ascii=False)

    def test_empty(self):
        assert build_packet(PROFILE, [])["jobs"] == []

    def test_missing_optional_fields_get_safe_defaults(self):
        entry = build_packet(PROFILE, [{"title": "T"}])["jobs"][0]
        assert entry["company"] == "" and entry["skills"] == [] and entry["rule_score"] == 0.0
        assert entry["guard"] == "clean"


def test_review_schema_documents_every_field_the_merger_reads():
    for field in ("key", "scores", "technical", "experience", "language", "career",
                  "location", "visa", "strengths", "gaps", "deadline", "gate_notes"):
        assert field in REVIEW_SCHEMA
