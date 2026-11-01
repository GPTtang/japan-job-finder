from job_finder.fetchers import _apply_source_filters, make_job


def _jobs():
    return [
        make_job(title="Python Dev", company="A", location="Tokyo", remote=True),
        make_job(title="Java Dev", company="B", location="Osaka", remote=False),
        make_job(title="Go Dev", company="C", location="", remote=None),
    ]


def test_no_filters_returns_input_unchanged():
    jobs = _jobs()
    out, issues = _apply_source_filters(jobs, None, "x")
    assert out == jobs and issues == []


def test_keyword_filter():
    out, _ = _apply_source_filters(_jobs(), {"keywords": ["python"]}, "x")
    assert [j["company"] for j in out] == ["A"]


def test_location_filter_keeps_jobs_without_location():
    out, _ = _apply_source_filters(_jobs(), {"locations": ["Tokyo"]}, "x")
    assert [j["company"] for j in out] == ["A", "C"]


def test_remote_only():
    out, _ = _apply_source_filters(_jobs(), {"remote_only": True}, "x")
    assert [j["company"] for j in out] == ["A"]


def test_remote_preferred_reorders_without_dropping():
    out, _ = _apply_source_filters(_jobs()[::-1], {"remote_preferred": True}, "x")
    assert out[0]["company"] == "A" and len(out) == 3


def test_all_removed_emits_warning():
    out, issues = _apply_source_filters(_jobs(), {"keywords": ["cobol"]}, "greenhouse")
    assert out == [] and issues[0].provider == "greenhouse"


def test_input_list_not_mutated():
    jobs = _jobs()
    _apply_source_filters(jobs, {"remote_preferred": True}, "x")
    assert [j["company"] for j in jobs] == ["A", "B", "C"]
