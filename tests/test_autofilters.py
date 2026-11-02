from job_finder.autofilters import (
    apply_dynamic_filters_to_sources,
    build_provider_filters_from_profile,
    merge_provider_filters,
)


def test_build_filters_dedupes_and_skips_remote_location():
    profile = {
        "target_roles": ["Backend Engineer"],
        "skills": ["python", "Python"],
        "keyword_terms": ["Backend Engineer"],
        "locations": ["Tokyo", "Remote"],
        "remote_preference": "only",
    }
    f = build_provider_filters_from_profile(profile)
    assert f["keywords"] == ["Backend Engineer", "python"]
    assert f["locations"] == ["Tokyo"]
    assert f["remote_only"] is True


def test_build_filters_remote_prefer():
    f = build_provider_filters_from_profile({"remote_preference": "prefer"})
    assert f == {"remote_preferred": True}


def test_build_filters_empty_profile():
    assert build_provider_filters_from_profile({}) == {}


def test_merge_unions_lists_static_first_case_insensitive():
    merged = merge_provider_filters({"keywords": ["Python"]}, {"keywords": ["python", "Go"]})
    assert merged["keywords"] == ["Python", "Go"]


def test_merge_booleans_and_extra_static_fields():
    merged = merge_provider_filters({"remote_only": True, "custom": 1}, {"remote_preferred": True})
    assert merged == {"remote_only": True, "remote_preferred": True, "custom": 1}


def test_merge_does_not_mutate_inputs():
    static = {"keywords": ["a"]}
    dynamic = {"keywords": ["b"]}
    merge_provider_filters(static, dynamic)
    assert static == {"keywords": ["a"]} and dynamic == {"keywords": ["b"]}


def test_apply_dynamic_keeps_separators_and_copies_sources():
    sources = [{"_comment": "x"}, {"provider": "japan_dev"}]
    out = apply_dynamic_filters_to_sources(sources, {"locations": ["Tokyo"]})
    assert out[0] == {"_comment": "x"}
    assert out[1]["filters"] == {"locations": ["Tokyo"]}
    assert "filters" not in sources[1]
