import json

import pytest

from job_finder.matcher import score_job
from job_finder.rerank.profile import load_profile_json, normalize_profile
from job_finder.signals import JLPT_RANK


def test_defaults_for_empty_input():
    p = normalize_profile({})
    assert p["target_roles"] == [] and p["skills"] == [] and p["locations"] == []
    assert p["jlpt_level"] is None and p["is_chinese_speaker"] is False
    assert p["visa_status"] == "unknown" and p["remote_preference"] is None
    assert p["deal_breakers"] == [] and p["years_experience"] is None


def test_valid_fields_are_kept():
    p = normalize_profile({
        "target_roles": ["Backend Engineer"], "skills": ["Python", "RAG"], "locations": ["Tokyo", "東京"],
        "jlpt_level": "N2", "is_chinese_speaker": True, "remote_preference": "prefer",
        "visa_status": "needs_sponsorship", "english_level": "business", "years_experience": 3,
        "deal_breakers": ["no sponsorship"], "notes": "likes startups",
    })
    assert p["jlpt_level"] == "N2" and p["is_chinese_speaker"] is True
    assert p["visa_status"] == "needs_sponsorship" and p["years_experience"] == 3
    assert p["deal_breakers"] == ["no sponsorship"] and p["notes"] == "likes startups"


@pytest.mark.parametrize("field,value", [
    ("jlpt_level", "N9"), ("jlpt_level", 2), ("remote_preference", "always"), ("visa_status", "citizen"),
    ("is_chinese_speaker", "yes"), ("years_experience", -1), ("years_experience", True),
    ("years_experience", 99), ("target_roles", "Backend"), ("skills", [1, None, ""]),
])
def test_invalid_values_fall_back_to_defaults(field, value):
    default = normalize_profile({})[field]
    assert normalize_profile({field: value})[field] == default


def test_lists_are_bounded_and_deduplicated():
    p = normalize_profile({"skills": ["Python", "python", "x" * 200] + [f"s{i}" for i in range(80)]})
    assert len(p["skills"]) <= 30 and p["skills"][0] == "Python"
    assert all(len(s) <= 40 for s in p["skills"]) and "python" not in p["skills"]


def test_unknown_keys_are_dropped():
    assert "evil" not in normalize_profile({"evil": "x", "skills": ["Go"]})


def test_free_text_is_bounded_and_single_spaced():
    p = normalize_profile({"notes": "a  b\n" + "x" * 900, "raw_query": "q" * 5000})
    assert len(p["notes"]) <= 500 and "\n" not in p["notes"] and len(p["raw_query"]) <= 2000


def test_regex_parser_fills_gaps_from_raw_query():
    p = normalize_profile({"raw_query": "Backend Engineer in Tokyo with Python, JLPT N2, native chinese"})
    assert "Backend Engineer" in p["target_roles"] and "Python" in p["skills"]
    assert p["jlpt_level"] == "N2" and p["is_chinese_speaker"] is True


def test_explicit_fields_override_the_regex_parser():
    p = normalize_profile({"raw_query": "Backend Engineer with Python", "skills": ["Rust"], "target_roles": []})
    assert p["skills"] == ["Rust"] and p["target_roles"] == []


def test_input_is_not_mutated():
    data = {"skills": ["Python"], "raw_query": "x"}
    snapshot = json.loads(json.dumps(data))
    normalize_profile(data)
    assert data == snapshot


@pytest.mark.parametrize("level", ["N4", "N5"])
def test_every_accepted_jlpt_level_can_be_scored(level):
    assert level in JLPT_RANK
    profile = normalize_profile({"jlpt_level": level})
    job = {"title": "Dev", "description": "JLPT N1 required", "skills": []}
    assert score_job(profile, job)["required_jlpt"] == "N1"


class TestLoadProfileJson:
    def test_parses_object(self):
        assert load_profile_json('{"skills": ["Go"]}')["skills"] == ["Go"]

    @pytest.mark.parametrize("text", ["", "{", "[]", '"x"', "null", "3"])
    def test_rejects_non_objects(self, text):
        with pytest.raises(ValueError):
            load_profile_json(text)
