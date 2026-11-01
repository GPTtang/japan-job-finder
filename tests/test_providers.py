"""Behavioural tests for every provider, driven through the public facade."""
import pytest
import requests

from job_finder.fetchers import (
    FetchIssue,
    FetchResult,
    fetch_all,
    fetch_ashby,
    fetch_browser_site,
    fetch_company_site,
    fetch_from_source,
    fetch_gaijinpot,
    fetch_greenhouse,
    fetch_japan_dev,
    fetch_lever,
    fetch_tokyodev,
    make_job,
    seed_jobs,
)
from tests.support import (
    FakeResponse,
    install_playwright,
    install_requests,
    json_ld_page,
    uninstall_playwright,
)

FAST = {"max_retries": 1, "retry_backoff_seconds": 0}


def messages(result):
    return [i.message for i in result.issues]


class TestGreenhouse:
    def test_maps_fields(self, monkeypatch):
        data = {"jobs": [{
            "title": "Backend Engineer", "absolute_url": "https://gh/1",
            "location": {"name": "Remote - Japan"}, "updated_at": "2026-10-02",
            "content": "&lt;p&gt;We use Python and Docker&lt;/p&gt;",
        }]}
        install_requests(monkeypatch, {"greenhouse.io": FakeResponse(json_data=data)})
        result = fetch_greenhouse("acme", FAST)
        job = result.jobs[0]
        assert job["company"] == "acme" and job["source"] == "greenhouse"
        assert job["remote"] is True and job["posted_date"] == "2026-10-02"
        assert job["description"] == "We use Python and Docker"
        assert {"Python", "Docker"} <= set(job["skills"])
        assert job["guard"] == "clean"

    def test_empty_board_warns(self, monkeypatch):
        install_requests(monkeypatch, {"greenhouse.io": FakeResponse(json_data={"jobs": []})})
        result = fetch_greenhouse("acme", FAST)
        assert result.jobs == [] and "No jobs returned from source" in messages(result)

    def test_http_error_is_an_issue_not_an_exception(self, monkeypatch):
        install_requests(monkeypatch, {"greenhouse.io": FakeResponse(404)})
        result = fetch_greenhouse("acme", FAST)
        assert result.jobs == [] and result.issues[0].message == "HTTP 404"
        assert result.issues[0].retryable is False

    def test_invalid_json_reported(self, monkeypatch):
        install_requests(monkeypatch, {"greenhouse.io": FakeResponse(200, text="<html>")})
        assert "Response was not valid JSON" in messages(fetch_greenhouse("acme", FAST))


class TestRetries:
    def test_network_error_then_success(self, monkeypatch):
        outcomes = iter([requests.ConnectionError("boom"), FakeResponse(json_data={"jobs": [
            {"title": "t", "content": ""}]})])
        install_requests(monkeypatch, {"greenhouse.io": lambda: next(outcomes)})
        result = fetch_greenhouse("acme", FAST)
        assert len(result.jobs) == 1
        assert result.issues[0].severity == "warning" and result.issues[0].retryable

    def test_network_error_exhausted(self, monkeypatch):
        calls = install_requests(monkeypatch, {"greenhouse.io": requests.Timeout("slow")})
        result = fetch_greenhouse("acme", FAST)
        assert len(calls) == 2 and result.jobs == []
        assert [i.severity for i in result.issues] == ["warning", "error"]

    def test_server_error_retried(self, monkeypatch):
        outcomes = iter([FakeResponse(503), FakeResponse(json_data={"jobs": []})])
        calls = install_requests(monkeypatch, {"greenhouse.io": lambda: next(outcomes)})
        fetch_greenhouse("acme", FAST)
        assert len(calls) == 2

    def test_zero_retries_means_single_attempt(self, monkeypatch):
        calls = install_requests(monkeypatch, {"greenhouse.io": requests.Timeout("x")})
        fetch_greenhouse("acme", {"max_retries": 0})
        assert len(calls) == 1


class TestLever:
    def test_maps_fields(self, monkeypatch):
        data = [{"text": "ML Engineer", "hostedUrl": "https://lv/1", "createdAt": 1700000000000,
                 "categories": {"location": "Tokyo / Remote"},
                 "descriptionPlain": "PyTorch role", "lists": [{"text": "Requires Python"}]}]
        install_requests(monkeypatch, {"lever.co": FakeResponse(json_data=data)})
        job = fetch_lever("acme", FAST).jobs[0]
        assert job["title"] == "ML Engineer" and job["remote"] is True
        assert {"PyTorch", "Python"} <= set(job["skills"])

    def test_empty_list_returns_no_jobs_and_no_warning(self, monkeypatch):
        # An empty payload is falsy, so Lever returns early without the "No jobs" warning.
        install_requests(monkeypatch, {"lever.co": FakeResponse(json_data=[])})
        result = fetch_lever("acme", FAST)
        assert result.jobs == [] and result.issues == []


class TestAshby:
    def test_prefers_plain_description(self, monkeypatch):
        data = {"jobs": [{"title": "SRE", "jobUrl": "https://ab/1", "location": "Tokyo",
                          "descriptionPlain": "Kubernetes", "descriptionHtml": "<p>ignored</p>",
                          "publishedDate": "2026-09-01"}]}
        install_requests(monkeypatch, {"ashbyhq.com": FakeResponse(json_data=data)})
        job = fetch_ashby("acme", FAST).jobs[0]
        assert job["description"] == "Kubernetes" and job["posted_date"] == "2026-09-01"

    def test_empty_warns(self, monkeypatch):
        install_requests(monkeypatch, {"ashbyhq.com": FakeResponse(json_data={"jobs": []})})
        assert "No jobs returned from source" in messages(fetch_ashby("acme", FAST))


class TestCompanySite:
    def test_json_ld_wins(self, monkeypatch):
        install_requests(monkeypatch, {"corp.example": FakeResponse(text=json_ld_page())})
        job = fetch_company_site("https://corp.example/careers", FAST).jobs[0]
        assert job["title"] == "Backend Engineer" and job["company"] == "Acme"
        assert job["posted_date"] == "2026-10-01" and job["remote"] is False

    def test_follows_career_link(self, monkeypatch):
        install_requests(monkeypatch, {
            "corp.example/careers/list": FakeResponse(text=json_ld_page(title="Child Job")),
            "corp.example": FakeResponse(text='<a href="/careers/list">Join us</a>'),
        })
        result = fetch_company_site("https://corp.example/", FAST)
        assert [j["title"] for j in result.jobs] == ["Child Job"]

    def test_heuristic_headings(self, monkeypatch):
        html = ("<title>Careers | Acme KK</title><h2>Backend Engineer</h2>"
                "<p>Python and AWS experience</p><h2>About us</h2>")
        install_requests(monkeypatch, {"corp.example": FakeResponse(text=html)})
        result = fetch_company_site("https://corp.example/", FAST)
        assert [(j["title"], j["company"]) for j in result.jobs] == [("Backend Engineer", "Acme KK")]
        assert "Python" in result.jobs[0]["skills"]
        assert result.issues == []

    def test_heuristic_table_cells_and_list_items(self, monkeypatch):
        install_requests(monkeypatch, {"a.example": FakeResponse(text="<table><td>Cloud Engineer</td></table>"),
                                       "b.example": FakeResponse(text="<ul><li>Project Manager</li></ul>")})
        assert fetch_company_site("https://a.example/", FAST).jobs[0]["title"] == "Cloud Engineer"
        assert fetch_company_site("https://b.example/", FAST).jobs[0]["title"] == "Project Manager"

    def test_company_falls_back_to_domain(self, monkeypatch):
        install_requests(monkeypatch, {"x.example": FakeResponse(text="<h2>Data Engineer</h2>")})
        assert fetch_company_site("https://www.x.example/", FAST).jobs[0]["company"] == "x.example"

    def test_nothing_found_warns(self, monkeypatch):
        install_requests(monkeypatch, {"corp.example": FakeResponse(text="<p>hello</p>")})
        result = fetch_company_site("https://corp.example/", FAST)
        assert result.jobs == [] and "No career links found" in messages(result)[0]

    def test_careers_page_without_jobs_warns_differently(self, monkeypatch):
        install_requests(monkeypatch, {
            "corp.example/jobs": FakeResponse(text="<p>none</p>"),
            "corp.example": FakeResponse(text='<a href="/jobs">Jobs</a>'),
        })
        result = fetch_company_site("https://corp.example/", FAST)
        assert "Careers page found but no jobs extracted" in messages(result)[0]

    def test_unreachable_site(self, monkeypatch):
        install_requests(monkeypatch, {"corp.example": FakeResponse(500)})
        result = fetch_company_site("https://corp.example/", FAST)
        assert result.jobs == [] and result.issues

    def test_charset_from_header_and_meta(self, monkeypatch):
        body = json_ld_page(title="日本語エンジニア").encode("shift_jis", errors="replace")
        resp = FakeResponse(headers={"content-type": "text/html; charset=shift_jis"})
        resp.content = body
        install_requests(monkeypatch, {"corp.example": resp})
        assert fetch_company_site("https://corp.example/", FAST).jobs

        meta = FakeResponse()
        meta.content = b'<meta charset="utf-8">' + json_ld_page(title="Meta").encode()
        install_requests(monkeypatch, {"corp.example": meta})
        assert fetch_company_site("https://corp.example/", FAST).jobs[0]["title"] == "Meta"


class TestBrowserSite:
    def test_without_playwright_degrades_to_issue(self, monkeypatch):
        uninstall_playwright(monkeypatch)
        result = fetch_browser_site("https://spa.example/", FAST)
        assert result.jobs == [] and "Playwright not installed" in messages(result)[0]

    def test_json_ld_from_rendered_page(self, monkeypatch):
        install_playwright(monkeypatch, {"https://spa.example/": json_ld_page()})
        assert fetch_browser_site("https://spa.example/", FAST).jobs[0]["title"] == "Backend Engineer"

    def test_next_data_blob(self, monkeypatch):
        blob = ('{"props":{"jobs":[{"title":"AI Engineer","company":"Neo","description":"RAG"}]}}')
        page = f'<script id="__NEXT_DATA__" type="application/json">{blob}</script>'
        install_playwright(monkeypatch, {"https://spa.example/": page})
        job = fetch_browser_site("https://spa.example/", FAST).jobs[0]
        assert (job["title"], job["company"], job["source"]) == ("AI Engineer", "Neo", "browser_site")

    def test_follows_links_found_in_rendered_page(self, monkeypatch):
        visited = install_playwright(monkeypatch, {
            "https://spa.example/": '<a href="/careers">c</a>',
            "https://spa.example/careers": json_ld_page(title="Linked"),
        })
        result = fetch_browser_site("https://spa.example/", FAST)
        assert [j["title"] for j in result.jobs] == ["Linked"] and len(visited) == 2

    def test_nothing_found_warns(self, monkeypatch):
        install_playwright(monkeypatch, {"https://spa.example/": "<p>empty</p>"})
        assert "no structured job data" in messages(fetch_browser_site("https://spa.example/", FAST))[0]

    def test_navigation_error_is_an_issue(self, monkeypatch):
        install_playwright(monkeypatch, {})
        result = fetch_browser_site("https://spa.example/", FAST)
        assert "Playwright error" in messages(result)[0] and result.issues[0].severity == "error"


class TestAggregators:
    def test_japan_dev_parses_rendered_listing(self, monkeypatch):
        html = ('<h2><a href="/jobs/acme-co/backend-engineer" class="job-item__title">'
                "Backend <b>Engineer</b></a></h2><div>Python and Docker work</div>")
        install_playwright(monkeypatch, {"https://japan-dev.com/jobs": html})
        job = fetch_japan_dev(FAST).jobs[0]
        assert job["title"] == "Backend Engineer" and job["company"] == "Acme Co"
        assert job["url"] == "https://japan-dev.com/jobs/acme-co/backend-engineer"
        assert "Python" in job["skills"]

    def test_japan_dev_falls_back_to_generic_extraction(self, monkeypatch):
        install_playwright(monkeypatch, {"https://japan-dev.com/jobs": json_ld_page(title="From LD")})
        install_requests(monkeypatch, {"japan-dev.com": FakeResponse(404)})
        assert fetch_japan_dev(FAST).jobs[0]["title"] == "From LD"

    def test_japan_dev_without_playwright(self, monkeypatch):
        uninstall_playwright(monkeypatch)
        assert fetch_japan_dev(FAST).jobs == []

    def test_tokyodev_slugs(self, monkeypatch):
        html = ('<a href="/companies/acme-co/jobs/senior-backend-engineer">x</a>'
                '<a href="/companies/acme-co/jobs/senior-backend-engineer">dup</a>')
        install_playwright(monkeypatch, {"https://www.tokyodev.com/jobs": html})
        jobs = fetch_tokyodev(FAST).jobs
        assert len(jobs) == 1
        assert (jobs[0]["title"], jobs[0]["company"]) == ("Senior Backend Engineer", "Acme Co")
        assert jobs[0]["location"] == "Tokyo, Japan"

    def test_tokyodev_no_slugs_reports_spa_warning(self, monkeypatch):
        install_playwright(monkeypatch, {"https://www.tokyodev.com/jobs": "<p>x</p>"})
        install_requests(monkeypatch, {"tokyodev.com": FakeResponse(text="<p>x</p>")})
        assert "Rails/Hotwire SPA" in messages(fetch_tokyodev(FAST))[-1]

    def test_gaijinpot_json_endpoint(self, monkeypatch):
        data = {"results": [{"title": "Bridge SE", "company": "Neusoft", "location": "Tokyo",
                             "url": "https://gp/1", "description": "<p>中国語</p>"}]}
        install_requests(monkeypatch, {"/job/index/search": FakeResponse(json_data=data)})
        job = fetch_gaijinpot(FAST).jobs[0]
        assert (job["title"], job["company"], job["url"]) == ("Bridge SE", "Neusoft", "https://gp/1")
        assert job["description"] == "中国語"

    def test_gaijinpot_falls_back_to_static_json_ld(self, monkeypatch):
        install_requests(monkeypatch, {
            "/job/index/search": FakeResponse(404),
            "jobs.gaijinpot.com": FakeResponse(text=json_ld_page(title="Static")),
        })
        assert fetch_gaijinpot(FAST).jobs[0]["title"] == "Static"

    def test_gaijinpot_nothing_found_warns(self, monkeypatch):
        install_requests(monkeypatch, {"gaijinpot.com": FakeResponse(text="<p>x</p>")})
        uninstall_playwright(monkeypatch)
        assert any("Django + client-side JS" in m for m in messages(fetch_gaijinpot(FAST)))


class TestDispatchAndFetchAll:
    def test_unsupported_provider(self):
        result = fetch_from_source({"provider": "nope"})
        assert result.issues[0].message == "Unsupported provider in source config"

    def test_missing_provider_key(self):
        assert fetch_from_source({}).provider == "unknown"

    @pytest.mark.parametrize("source,fragment", [
        ({"provider": "greenhouse", "token": "t"}, "greenhouse.io"),
        ({"provider": "lever", "company": "c"}, "lever.co"),
        ({"provider": "ashby", "board": "b"}, "ashbyhq.com"),
        ({"provider": "company_site", "url": "https://corp.example/"}, "corp.example"),
    ])
    def test_dispatch_routes_to_the_right_endpoint(self, monkeypatch, source, fragment):
        calls = install_requests(monkeypatch, {})
        fetch_from_source(source, FAST)
        assert any(fragment in c for c in calls)

    def test_dispatch_browser_providers(self, monkeypatch):
        visited = install_playwright(monkeypatch, {})
        for source in ({"provider": "browser_site", "url": "https://spa.example/"},
                       {"provider": "japan_dev"}, {"provider": "tokyodev"}):
            fetch_from_source(source, FAST)
        assert visited[0] == "https://spa.example/" and len(visited) >= 3

    def test_source_filters_applied_after_fetch(self, monkeypatch):
        data = {"jobs": [{"title": "Python Dev", "content": ""}, {"title": "Cobol Dev", "content": ""}]}
        install_requests(monkeypatch, {"greenhouse.io": FakeResponse(json_data=data)})
        source = {"provider": "greenhouse", "token": "t", "filters": {"keywords": ["python"]}}
        assert [j["title"] for j in fetch_from_source(source, FAST).jobs] == ["Python Dev"]

    def test_fetch_all_merges_and_skips_separators(self, monkeypatch):
        install_requests(monkeypatch, {
            "greenhouse.io": FakeResponse(json_data={"jobs": [{"title": "A", "content": ""}]}),
            "lever.co": FakeResponse(500),
        })
        sources = [{"_comment": "ignored"}, {"provider": "greenhouse", "token": "t"},
                   {"provider": "lever", "company": "c"}]
        out = fetch_all(sources, {"max_retries": 0})
        assert [j["title"] for j in out["jobs"]] == ["A"]
        assert out["issues"][0]["provider"] == "lever"

    def test_fetch_all_with_nothing_to_do(self):
        assert fetch_all([{"_x": 1}]) == {"jobs": [], "issues": []}
        assert fetch_all([]) == {"jobs": [], "issues": []}

    def test_fetch_all_sequential_mode(self, monkeypatch):
        install_requests(monkeypatch, {"greenhouse.io": FakeResponse(json_data={"jobs": [
            {"title": "A", "content": ""}]})})
        out = fetch_all([{"provider": "greenhouse", "token": "t"}], {"max_concurrent_fetches": 1})
        assert len(out["jobs"]) == 1

    def test_fetch_all_survives_provider_crash(self, monkeypatch):
        install_requests(monkeypatch, {"greenhouse.io": ValueError("kaboom")})
        out = fetch_all([{"provider": "greenhouse", "token": "t"}], {})
        assert out["jobs"] == [] and "kaboom" in out["issues"][0]["message"]
        assert out["issues"][0]["provider"] == "greenhouse"

    def test_fetch_all_invalid_concurrency_uses_default(self, monkeypatch):
        install_requests(monkeypatch, {"greenhouse.io": FakeResponse(json_data={"jobs": []})})
        out = fetch_all([{"provider": "greenhouse", "token": "t"}], {"max_concurrent_fetches": 0})
        assert out["jobs"] == []


class TestModels:
    def test_fetch_result_ok_ignores_warnings(self):
        assert FetchResult("p", issues=[FetchIssue("p", "m", severity="warning")]).ok
        assert not FetchResult("p", issues=[FetchIssue("p", "m", severity="error")]).ok

    def test_seed_jobs_shape(self):
        jobs = seed_jobs()
        assert jobs and all({"title", "company", "guard"} <= j.keys() for j in jobs)

    def test_make_job_defaults(self):
        job = make_job(title="", company="")
        assert job["skills"] == [] and job["remote"] is None and job["url"] == ""
