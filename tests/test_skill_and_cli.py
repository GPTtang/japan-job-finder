import json

import pytest

from job_finder import skill
from job_finder.cli import main

JOB = {"title": "Backend Engineer", "company": "Acme", "location": "Tokyo",
       "url": "u", "description": "", "skills": ["Python"], "source": "t"}


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({"sources": [{"provider": "japan_dev"}]}), encoding="utf-8")
    return str(p)


@pytest.fixture
def fake_fetch(monkeypatch):
    calls = []

    def _fetch_all(sources, fetch_options=None):
        calls.append(sources)
        return {"jobs": [dict(JOB)], "issues": []}

    monkeypatch.setattr(skill, "fetch_all", _fetch_all)
    return calls


def test_run_returns_ranked_jobs(config_file, fake_fetch):
    payload = skill.run_job_finder("Backend Engineer in Tokyo with Python", config_path=config_file)
    assert payload["ok"] and payload["jobs"][0]["company"] == "Acme"
    assert payload["effective_sources"][0]["filters"]["locations"]


def test_run_missing_config_is_config_error(tmp_path):
    payload = skill.run_job_finder("x", config_path=str(tmp_path / "none.json"))
    assert not payload["ok"] and payload["error_type"] == "config_error"


def test_run_invalid_json_is_config_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{", encoding="utf-8")
    assert not skill.run_job_finder("x", config_path=str(p))["ok"]


def test_run_validation_errors_are_reported(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"sources": [{"provider": "nope"}]}), encoding="utf-8")
    payload = skill.run_job_finder("x", config_path=str(p))
    assert not payload["ok"] and payload["errors"]


def test_config_warnings_surface_as_issues(tmp_path, fake_fetch):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"sources": []}), encoding="utf-8")
    payload = skill.run_job_finder("x", config_path=str(p))
    assert payload["issues"][0]["provider"] == "config"


def test_job_finder_text_report(config_file, fake_fetch):
    text = skill.job_finder("Backend Engineer Tokyo Python", config_path=config_file)
    assert text.startswith("# 求职匹配报告")


def test_job_finder_config_error_text(tmp_path):
    text = skill.job_finder("x", config_path=str(tmp_path / "none.json"))
    assert text.startswith("# 配置错误")


class TestCli:
    def test_text_output(self, config_file, fake_fetch, capsys):
        assert main(["Backend Engineer Tokyo", "--config", config_file]) == 0
        assert "求职匹配报告" in capsys.readouterr().out

    def test_json_output(self, config_file, fake_fetch, capsys):
        assert main(["Backend Engineer", "--config", config_file, "--output", "json", "--pretty"]) == 0
        assert json.loads(capsys.readouterr().out)["ok"] is True

    def test_json_config_error_exit_code(self, tmp_path, capsys):
        assert main(["x", "--config", str(tmp_path / "none.json"), "--output", "json"]) == 1

    def test_missing_query_exits_2(self, capsys):
        assert main([]) == 2

    def test_query_file(self, tmp_path, config_file, fake_fetch, capsys):
        q = tmp_path / "q.txt"
        q.write_text("Backend Engineer", encoding="utf-8")
        assert main(["--query-file", str(q), "--config", config_file]) == 0
