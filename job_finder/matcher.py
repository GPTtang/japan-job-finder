from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .signals import (
    BRIDGE_ONLY_SIGNALS,
    BRIDGE_SE_SIGNALS,
    CHINESE_ADVANTAGE_SIGNALS,
    JLPT_RANK,
    JLPT_REQUIREMENT_MAP,
    has_any_term,
    has_term,
)


class MatchRecord(dict):
    """Dictionary-backed record that also exposes attribute access."""

    def __getattr__(self, key: str):  # pragma: no cover
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value):  # pragma: no cover
        self[key] = value

    def copy(self):  # pragma: no cover
        return MatchRecord(self)


def _overlap(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    sa = {x.lower() for x in a}
    sb = {x.lower() for x in b}
    return len(sa & sb) / max(len(sa), 1)


def _detect_chinese_advantage(job_text: str) -> bool:
    """Return True if the job description signals Chinese speaker is preferred."""
    return has_any_term(job_text, CHINESE_ADVANTAGE_SIGNALS)


def _detect_bridge_se(job_text: str) -> bool:
    """Return True if the role involves Bridge SE / offshore coordination."""
    return has_any_term(job_text, BRIDGE_SE_SIGNALS)


def _detect_jlpt_requirement(job_text: str) -> str | None:
    """Extract the minimum JLPT level required from job text."""
    found = [
        level for pattern, level in JLPT_REQUIREMENT_MAP.items()
        if has_term(job_text, pattern)
    ]
    if not found:
        return None
    # Return the strictest (most demanding) requirement found so the penalty is
    # applied correctly when a job signals e.g. both N2 and N3 in the same text.
    return min(found, key=lambda x: JLPT_RANK[x])


def _check_priority(
    job: Dict[str, object],
    priority_cfg: Dict[str, Any],
) -> Tuple[bool, float, Optional[str]]:
    """Return (is_priority, boost, label) for the job against priority_companies config."""
    if not priority_cfg:
        return False, 0.0, None

    meta = priority_cfg.get("_meta") or {}
    named_boost = float(meta.get("priority_boost", 0.25))
    chinese_boost = float(meta.get("chinese_company_boost", 0.20))

    job_url = str(job.get("url", "")).lower()
    job_company = str(job.get("company", "")).lower()

    # ── Check named companies first (highest priority) ────────────────
    for company in priority_cfg.get("named_companies") or []:
        for pat in company.get("url_patterns") or []:
            if pat.lower() in job_url:
                return True, named_boost, company["name"]
        for pat in company.get("name_patterns") or []:
            if pat.lower() in job_company:
                return True, named_boost, company["name"]

    # ── Check Chinese IT company signals (secondary) ──────────────────
    signals = priority_cfg.get("chinese_it_signals") or {}
    for pat in signals.get("url_domain_patterns") or []:
        if pat.lower() in job_url:
            return True, chinese_boost, "中国系IT乙方"
    for pat in signals.get("company_name_patterns") or []:
        if pat.lower() in job_company:
            return True, chinese_boost, "中国系IT乙方"

    job_text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    min_signals = int(signals.get("min_signals_for_boost", 1))
    text_hits = sum(
        1 for sig in (signals.get("job_text_signals") or [])
        if sig.lower() in job_text
    )
    if text_hits >= min_signals:
        return True, chinese_boost, "中国系IT乙方（テキスト判定）"

    return False, 0.0, None


def score_job(
    profile: Dict[str, object],
    job: Dict[str, object],
    priority_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, object]:
    title = str(job.get("title", ""))
    location = str(job.get("location", ""))
    description = str(job.get("description", ""))
    job_text = f"{title} {description}".lower()

    target_roles = profile.get("target_roles", []) or []
    target_locations = profile.get("locations", []) or []
    target_skills = profile.get("skills", []) or []
    is_chinese_speaker = bool(profile.get("is_chinese_speaker", False))
    candidate_jlpt = profile.get("jlpt_level")  # e.g. "N2"

    # ── Base scores ──────────────────────────────────────────────────
    title_match = 0.0
    if target_roles:
        title_l = title.lower()
        title_match = max(1.0 if role.lower() in title_l else 0.0 for role in target_roles)

    location_match = 0.0
    if target_locations:
        loc_l = location.lower()
        location_match = max(1.0 if loc.lower() in loc_l else 0.0 for loc in target_locations)

    skill_match = _overlap(target_skills, job.get("skills", []) or [])

    # ── Bonus: Chinese speaker advantage ─────────────────────────────
    chinese_advantage = _detect_chinese_advantage(job_text)
    chinese_bonus = 0.15 if (is_chinese_speaker and chinese_advantage) else 0.0

    # ── Bonus: Bridge SE role (high value for bilingual candidates) ───
    is_bridge_se = _detect_bridge_se(job_text)
    bridge_specific = has_any_term(job_text, BRIDGE_ONLY_SIGNALS)
    bridge_bonus = 0.10 if (is_chinese_speaker and bridge_specific) else 0.0

    # ── Bonus: priority company (user-specified or Chinese IT 乙方) ───
    is_priority, priority_boost, priority_label = _check_priority(job, priority_cfg or {})

    # ── Penalty: JLPT requirement exceeds candidate level ────────────
    required_jlpt = _detect_jlpt_requirement(job_text)
    jlpt_penalty = 0.0
    if required_jlpt and candidate_jlpt:
        if JLPT_RANK[required_jlpt] < JLPT_RANK[candidate_jlpt]:
            jlpt_penalty = 0.20  # job requires better Japanese than candidate has

    # ── Final score ───────────────────────────────────────────────────
    base = 0.5 * skill_match + 0.3 * title_match + 0.2 * location_match
    match_score = round(
        max(0.0, min(1.0, base + chinese_bonus + bridge_bonus + priority_boost) - jlpt_penalty),
        3,
    )

    # ── Reasons ───────────────────────────────────────────────────────
    reasons = []
    for skill in target_skills:
        if skill.lower() in {s.lower() for s in (job.get("skills", []) or [])}:
            reasons.append(f"技能命中：{skill}")
    if target_roles and title_match > 0:
        reasons.append("职位标题与目标方向接近")
    if target_locations and location_match > 0:
        reasons.append("地点偏好匹配")
    if chinese_advantage and is_chinese_speaker:
        reasons.append("中国語・中文優遇ポジション（加点）")
    if is_bridge_se and is_chinese_speaker:
        reasons.append("Bridge SE / オフショア連携職（加点）")
    if is_priority and priority_label:
        reasons.append(f"ユーザー指定優先企業：{priority_label}（+{priority_boost:.0%}加点）")

    # ── Gaps ─────────────────────────────────────────────────────────
    gaps = []
    candidate_skills_l = {s.lower() for s in target_skills}
    for maybe_gap in ["AWS", "Kubernetes", "Go", "React", "SAP", "COBOL"]:
        if maybe_gap.lower() in job_text and maybe_gap.lower() not in candidate_skills_l:
            gaps.append(maybe_gap)
    if required_jlpt and jlpt_penalty > 0:
        gaps.append(f"日本語要件：{required_jlpt}（現状より高い可能性）")

    enriched = MatchRecord(job)
    enriched["match_score"] = match_score
    enriched["fit_reasons"] = reasons[:5]
    enriched["gaps"] = gaps[:4]
    enriched["chinese_advantage"] = chinese_advantage
    enriched["is_bridge_se"] = is_bridge_se
    enriched["required_jlpt"] = required_jlpt
    enriched["is_priority_company"] = is_priority
    enriched["priority_label"] = priority_label
    return enriched


def rank_jobs(
    profile: Dict[str, object],
    jobs: List[Dict[str, object]],
    top_n: int = 5,
    priority_cfg: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, object]]:
    ranked = [score_job(profile, job, priority_cfg=priority_cfg) for job in jobs]
    ranked.sort(
        key=lambda x: (x.get("match_score", 0), x.get("company", ""), x.get("title", "")),
        reverse=True,
    )
    return ranked[:top_n]
