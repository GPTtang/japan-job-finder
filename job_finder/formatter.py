from __future__ import annotations

from typing import Dict, List


def build_report_payload(profile: Dict[str, object], jobs: List[Dict[str, object]], issues: List[Dict[str, object]] | None = None) -> Dict[str, object]:
    return {
        "summary": {
            "target_roles": profile.get("target_roles", []) or [],
            "locations": profile.get("locations", []) or [],
            "skills": profile.get("skills", []) or [],
            "job_count": len(jobs),
        },
        "issues": issues or [],
        "jobs": jobs,
        "suggestions": [
            {
                "company": job.get("company", "Unknown"),
                "title": job.get("title", "Untitled"),
                "match_score": job.get("match_score", 0),
            }
            for job in jobs[:3]
        ],
    }


def format_job_report(profile: Dict[str, object], jobs: List[Dict[str, object]], issues: List[Dict[str, object]] | None = None) -> str:
    lines: List[str] = []
    roles = ", ".join(profile.get("target_roles", []) or []) or "未明确职位方向"
    locations = ", ".join(profile.get("locations", []) or []) or "未明确地点偏好"
    skills = ", ".join(profile.get("skills", []) or []) or "未提取到明确技能"

    lines.append("# 求职匹配报告")
    lines.append("")
    lines.append("## 整体结论")
    lines.append(f"- 目标岗位：{roles}")
    lines.append(f"- 地点偏好：{locations}")
    lines.append(f"- 识别到的技能：{skills}")
    lines.append(f"- 本次返回岗位数：{len(jobs)}")
    lines.append("")

    if issues:
        lines.append("## 抓取状态")
        for issue in issues[:8]:
            sev = issue.get("severity", "warning")
            provider = issue.get("provider", "unknown")
            msg = issue.get("message", "")
            lines.append(f"- [{sev}] {provider}: {msg}")
        lines.append("")

    if not jobs:
        lines.append("## 结果")
        lines.append("这次没有找到强匹配岗位。建议放宽职位标题、地点或技能关键词后再试。")
        return "\n".join(lines)

    lines.append("## 推荐岗位")
    for idx, job in enumerate(jobs, start=1):
        # Build badges
        badges = []
        if job.get("chinese_advantage"):
            badges.append("中国語優遇")
        if job.get("is_bridge_se"):
            badges.append("Bridge SE")
        if job.get("required_jlpt"):
            badges.append(f"日語{job['required_jlpt']}+")
        badge_str = f" [{' | '.join(badges)}]" if badges else ""
        guard_verdict = str(job.get("guard") or "clean")
        warn_str = " ⚠" if guard_verdict != "clean" else ""

        lines.append(f"### {idx}. {job.get('company', 'Unknown')} — {job.get('title', 'Untitled')}{badge_str}{warn_str}")
        lines.append(f"- 地点：{job.get('location', 'Unknown')}")
        lines.append(f"- 来源：{job.get('source', 'Unknown')}")
        if job.get("url"):
            lines.append(f"- 链接：{job.get('url')}")
        lines.append(f"- 匹配分：{job.get('match_score', 0)}")
        if guard_verdict != "clean":
            lines.append(f"- 内容安全：{guard_verdict}（该岗位文本含可疑内容，已清洗后评分，请人工核对原帖）")
        reasons = job.get("fit_reasons", []) or []
        gaps = job.get("gaps", []) or []
        if reasons:
            lines.append(f"- 匹配理由：{'；'.join(reasons)}")
        if gaps:
            lines.append(f"- 可能短板：{'；'.join(gaps)}")
        lines.append("")

    if jobs:
        lines.append("## 投递建议")
        top = jobs[:3]
        for job in top:
            lines.append(f"- 优先看：{job.get('company', 'Unknown')} / {job.get('title', 'Untitled')}（匹配分 {job.get('match_score', 0)}）")

    return "\n".join(lines)
