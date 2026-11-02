from job_finder.matcher import (
    _detect_bridge_se,
    _detect_chinese_advantage,
    _detect_jlpt_requirement,
    rank_jobs,
    score_job,
)

PROFILE = {
    "target_roles": ["Backend Engineer"],
    "locations": ["Tokyo"],
    "skills": ["Python", "FastAPI"],
    "is_chinese_speaker": True,
    "jlpt_level": "N2",
}


def _job(**overrides):
    base = {
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Tokyo",
        "url": "https://acme.example/jobs/1",
        "description": "Build services.",
        "skills": ["Python", "FastAPI"],
    }
    return {**base, **overrides}


class TestDetectors:
    def test_chinese_advantage_detected(self):
        assert _detect_chinese_advantage("中国語が話せる方歓迎")

    def test_chinese_advantage_absent(self):
        assert not _detect_chinese_advantage("python backend developer")

    def test_bridge_se_detected(self):
        assert _detect_bridge_se("ブリッジSE募集")

    def test_jlpt_picks_strictest(self):
        assert _detect_jlpt_requirement("JLPT N2 or n3 preferred") == "N2"

    def test_jlpt_none_when_absent(self):
        assert _detect_jlpt_requirement("english only") is None

    def test_jlpt_business_japanese_maps_to_n2(self):
        assert _detect_jlpt_requirement("business japanese required") == "N2"

    def test_jlpt_ignores_substring_in_other_words(self):
        # "gen2" / "spring3" contain "n2" / "n3" but are not JLPT levels
        assert _detect_jlpt_requirement("experience with Gen2 and Spring3 stacks") is None


class TestScoreJob:
    def test_full_match_has_no_bonus_or_penalty(self):
        result = score_job(PROFILE, _job())
        assert result["match_score"] == 1.0
        assert result["gaps"] == []

    def test_does_not_mutate_input_job(self):
        job = _job()
        snapshot = dict(job)
        score_job(PROFILE, job)
        assert job == snapshot

    def test_chinese_bonus_requires_chinese_speaker(self):
        job = _job(title="Engineer", location="Osaka", skills=[], description="chinese speaker welcome")
        with_flag = score_job(PROFILE, job)["match_score"]
        without = score_job({**PROFILE, "is_chinese_speaker": False}, job)["match_score"]
        assert round(with_flag - without, 2) == 0.15

    def _bonus(self, description):
        job = _job(title="Engineer", location="Osaka", skills=[], description=description)
        with_flag = score_job(PROFILE, job)["match_score"]
        without = score_job({**PROFILE, "is_chinese_speaker": False}, job)["match_score"]
        return round(with_flag - without, 2)

    def test_shared_signal_is_counted_once(self):
        # "中国語" is both a language cue and a Bridge SE cue; it must not earn both bonuses.
        assert self._bonus("中国語歓迎") == 0.15

    def test_bridge_specific_signal_earns_the_bridge_bonus(self):
        assert self._bonus("対中ビジネスの窓口") == 0.10

    def test_both_kinds_of_signal_stack(self):
        assert self._bonus("中国語歓迎。対中ビジネスの窓口") == 0.25

    def test_office_city_alone_is_not_a_chinese_language_signal(self):
        assert self._bonus("本社は上海、北京、深圳にオフィスがあります") == 0.0

    def test_offshore_hub_city_still_counts(self):
        assert self._bonus("大連の開発センターと連携") == 0.15

    def test_jlpt_penalty_applied_when_job_requires_higher_level(self):
        job = _job(description="JLPT N1 required")
        result = score_job(PROFILE, job)
        assert result["required_jlpt"] == "N1"
        assert result["match_score"] == 0.8
        assert any("N1" in g for g in result["gaps"])

    def test_no_jlpt_penalty_when_candidate_level_unknown(self):
        job = _job(description="JLPT N1 required")
        result = score_job({**PROFILE, "jlpt_level": None}, job)
        assert result["match_score"] == 1.0

    def test_skill_gap_listed(self):
        job = _job(description="We use Kubernetes and AWS")
        assert {"AWS", "Kubernetes"} <= set(score_job(PROFILE, job)["gaps"])

    def test_score_is_clamped_to_unit_interval(self):
        cfg = {"_meta": {"priority_boost": 0.9}, "named_companies": [
            {"name": "Acme", "name_patterns": ["acme"]}]}
        job = _job(description="中国語 bridge se")
        assert score_job(PROFILE, job, priority_cfg=cfg)["match_score"] == 1.0


class TestPriorityCompanies:
    CFG = {
        "_meta": {"priority_boost": 0.25, "chinese_company_boost": 0.20},
        "named_companies": [
            {"name": "Named Co", "name_patterns": ["namedco"], "url_patterns": ["namedco.jp"]}
        ],
        "chinese_it_signals": {
            "company_name_patterns": ["neusoft"],
            "url_domain_patterns": [],
            "job_text_signals": ["対中", "中国向け"],
            "min_signals_for_boost": 1,
        },
    }

    def _score(self, **overrides):
        job = _job(title="x", location="x", skills=[], **overrides)
        return score_job({"is_chinese_speaker": False}, job, priority_cfg=self.CFG)

    def test_named_company_by_name(self):
        r = self._score(company="NamedCo KK")
        assert r["is_priority_company"] and r["priority_label"] == "Named Co"
        assert r["match_score"] == 0.25

    def test_named_company_by_url(self):
        r = self._score(url="https://careers.namedco.jp/1")
        assert r["priority_label"] == "Named Co"

    def test_chinese_it_by_company_name(self):
        r = self._score(company="Neusoft Japan")
        assert r["priority_label"] == "中国系IT乙方"
        assert r["match_score"] == 0.20

    def test_chinese_it_by_text_signal(self):
        r = self._score(description="対中ビジネスの案件")
        assert "テキスト判定" in r["priority_label"]

    def test_no_config_means_no_priority(self):
        r = score_job({"is_chinese_speaker": False}, _job(), priority_cfg=None)
        assert not r["is_priority_company"]


class TestRankJobs:
    def test_sorted_descending_and_truncated(self):
        jobs = [
            _job(title="Other", location="Osaka", skills=[]),
            _job(),
            _job(title="Backend Engineer", location="Osaka", skills=["Python"]),
        ]
        ranked = rank_jobs(PROFILE, jobs, top_n=2)
        assert len(ranked) == 2
        assert ranked[0]["match_score"] >= ranked[1]["match_score"]
        assert ranked[0]["match_score"] == 1.0

    def test_empty_input(self):
        assert rank_jobs(PROFILE, []) == []
