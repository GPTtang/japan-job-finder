from job_finder.rerank.merge import merge_reviews
from job_finder.rerank.packet import build_packet, job_key
from job_finder.rerank.profile import normalize_profile
from job_finder.rerank.report import format_reviewed_report

PROFILE = normalize_profile({"raw_query": "东京后端", "target_roles": ["Backend Engineer"],
                             "locations": ["Tokyo"], "skills": ["Python"]})


def posting(n, **overrides):
    base = {"title": f"Job {n}", "company": f"Co {n}", "location": "Tokyo", "url": f"https://x.example/{n}",
            "description": "d", "skills": [], "source": "freehire", "guard": "clean", "match_score": 0.5,
            "posted_date": "2026-10-20"}
    return {**base, **overrides}


def review(job, **overrides):
    base = {"key": job_key(job), "scores": {"technical": 80, "experience": 70, "language": 60, "career": 90},
            "location": "PASS", "language": "PASS", "visa": "PASS", "gate_notes": {},
            "strengths": ["Python 技能匹配"], "gaps": ["缺少 AWS"], "deadline": None}
    return {**base, **overrides}


def render(jobs, reviews):
    packet = build_packet(PROFILE, jobs)
    return format_reviewed_report(PROFILE, merge_reviews(packet, reviews))


def test_ranked_section_shows_scores_reasons_and_link():
    a = posting(1)
    text = render([a], [review(a)])
    assert text.startswith("# 求职匹配报告（精排）")
    assert "### 1. Co 1 — Job 1" in text and "强匹配" in text and "76.0" in text
    assert "技术 80" in text and "经验 70" in text and "语言 60" in text and "方向 90" in text
    assert "Python 技能匹配" in text and "缺少 AWS" in text and "https://x.example/1" in text
    assert "目标岗位：Backend Engineer" in text


def test_states_that_scores_are_triage_from_posting_text():
    a = posting(1)
    assert "仅基于岗位文本" in render([a], [review(a)])


def test_flags_add_a_marker_and_note():
    a = posting(1)
    text = render([a], [review(a, visa="FLAG", gate_notes={"visa": "未说明是否提供签证"})])
    assert "### 1. Co 1 — Job 1 ⚠" in text and "未说明是否提供签证" in text


def test_clean_posting_has_no_marker():
    a = posting(1)
    assert "⚠" not in render([a], [review(a)]).split("## 提示")[0]


def test_deadline_is_shown_when_present():
    a = posting(1)
    assert "截止：2026-12-31" in render([a], [review(a, deadline="2026-12-31")])


def test_excluded_section_lists_reason_and_link():
    a = posting(1)
    text = render([a], [review(a, location="FAIL", gate_notes={"location": "需要搬到大阪"})])
    assert "## 已排除" in text and "需要搬到大阪" in text and "https://x.example/1" in text
    assert "## 推荐岗位" not in text


def test_unreviewed_section_explains_and_orders_by_rule_score():
    a, b = posting(1, match_score=0.2), posting(2, match_score=0.9)
    text = render([a, b], [])
    assert "## 未完成精排" in text and text.index("Job 2") < text.index("Job 1")


def test_issues_are_listed_once():
    a = posting(1)
    text = render([a], [review(a), {"key": "unknown"}])
    assert "## 处理说明" in text and text.count("key 未知或缺失") == 1


def test_no_issue_section_when_all_is_well():
    a = posting(1)
    assert "## 处理说明" not in render([a], [review(a)])


def test_non_http_links_are_not_rendered():
    a = posting(1, url="javascript:alert(1)")
    text = render([a], [review(a)])
    assert "javascript:" not in text


def test_counts_line():
    a, b, c = posting(1), posting(2), posting(3)
    text = render([a, b, c], [review(a), review(b, visa="FAIL")])
    assert "入榜 1 · 排除 1 · 未精排 1" in text
