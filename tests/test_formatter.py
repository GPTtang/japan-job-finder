from job_finder.formatter import build_report_payload, format_job_report

PROFILE = {"target_roles": ["Backend Engineer"], "locations": ["Tokyo"], "skills": ["Python"]}
JOB = {
    "company": "Acme", "title": "Dev", "location": "Tokyo", "source": "x",
    "url": "https://e.example/1", "match_score": 0.9, "fit_reasons": ["r1", "r2"],
    "gaps": ["AWS"], "chinese_advantage": True, "is_bridge_se": True, "required_jlpt": "N2",
}


def test_payload_summary_and_suggestions_limited_to_three():
    payload = build_report_payload(PROFILE, [JOB] * 5)
    assert payload["summary"]["job_count"] == 5
    assert len(payload["suggestions"]) == 3
    assert payload["issues"] == []


def test_report_empty_jobs_message():
    text = format_job_report({}, [])
    assert "没有找到强匹配岗位" in text and "未明确职位方向" in text


def test_report_includes_badges_links_and_gaps():
    text = format_job_report(PROFILE, [JOB])
    assert "[中国語優遇 | Bridge SE | 日語N2+]" in text
    assert "https://e.example/1" in text
    assert "r1；r2" in text and "AWS" in text


def test_report_lists_at_most_eight_issues():
    issues = [{"severity": "warning", "provider": f"p{i}", "message": "m"} for i in range(12)]
    text = format_job_report(PROFILE, [JOB], issues=issues)
    assert "p7" in text and "p8" not in text
