"""Render a merged review result as a Markdown report."""
from __future__ import annotations

from typing import Any, List, Mapping

_DIMENSION_LABELS = (("technical", "技术"), ("experience", "经验"), ("language", "语言"), ("career", "方向"))


def _link(url: Any) -> str:
    return url if isinstance(url, str) and url.startswith(("http://", "https://")) else ""


def _header(profile: Mapping[str, Any], merged: Mapping[str, Any]) -> List[str]:
    summary = merged["summary"]
    roles = ", ".join(profile.get("target_roles") or []) or "未明确职位方向"
    places = ", ".join(profile.get("locations") or []) or "未明确地点偏好"
    skills = ", ".join(profile.get("skills") or []) or "未提取到明确技能"
    return [
        "# 求职匹配报告（精排）", "",
        "## 整体结论",
        f"- 目标岗位：{roles}",
        f"- 地点偏好：{places}",
        f"- 识别到的技能：{skills}",
        f"- 评审候选 {summary['total']} 条：入榜 {summary['ranked']} · 排除 {summary['excluded']}"
        f" · 未精排 {summary['unreviewed']}",
        "- 说明：综合分由 AI 仅基于岗位文本和你的画像初筛得出，不含公司调研；投递前请核对原帖。",
        "",
    ]


def _ranked_block(index: int, item: Mapping[str, Any]) -> List[str]:
    marker = " ⚠" if item["flags"] else ""
    parts = " · ".join(f"{label} {item['scores'][name]:.0f}" for name, label in _DIMENSION_LABELS)
    lines = [
        f"### {index}. {item['company'] or 'Unknown'} — {item['title'] or 'Untitled'}{marker}",
        f"- 综合分：{item['overall']}（{item['band']}）｜{parts}",
        f"- 地点：{item['location'] or 'Unknown'}｜来源：{item['source'] or 'Unknown'}",
    ]
    if _link(item["url"]):
        lines.append(f"- 链接：{item['url']}")
    if item["deadline"]:
        lines.append(f"- 截止：{item['deadline']}")
    if item["strengths"]:
        lines.append(f"- 优势：{'；'.join(item['strengths'])}")
    if item["gaps"]:
        lines.append(f"- 短板：{'；'.join(item['gaps'])}")
    lines.extend(f"- 注意：{flag}" for flag in item["flags"])
    lines.append("")
    return lines


def _excluded_block(item: Mapping[str, Any]) -> str:
    reasons = "；".join(item["excluded_reasons"])
    link = f" — {item['url']}" if _link(item["url"]) else ""
    return f"- {item['title']} @ {item['company']}（综合分 {item['overall']}）— {reasons}{link}"


def _unreviewed_block(item: Mapping[str, Any]) -> str:
    link = f" — {item['url']}" if _link(item["url"]) else ""
    return f"- 规则分 {float(item['rule_score'] or 0):.2f}｜{item['title']} @ {item['company']}{link}"


MAX_FETCH_ISSUES = 8


def _fetch_block(merged: Mapping[str, Any]) -> List[str]:
    issues = merged.get("fetch_issues") or []
    if not issues:
        return []
    lines = ["## 抓取状态"]
    for issue in issues[:MAX_FETCH_ISSUES]:
        lines.append(f"- [{issue.get('severity', 'warning')}] {issue.get('provider', 'unknown')}: "
                     f"{issue.get('message', '')}")
    lines.append("")
    return lines


def format_reviewed_report(profile: Mapping[str, Any], merged: Mapping[str, Any]) -> str:
    lines = _header(profile, merged)
    lines.extend(_fetch_block(merged))
    if merged["ranked"]:
        lines.append("## 推荐岗位")
        for index, item in enumerate(merged["ranked"], start=1):
            lines.extend(_ranked_block(index, item))
    if merged["excluded"]:
        lines.append("## 已排除")
        lines.extend(_excluded_block(item) for item in merged["excluded"])
        lines.append("")
    if merged["unreviewed"]:
        lines.append("## 未完成精排")
        lines.append("以下岗位没有拿到有效评审，仅按规则初筛分排序：")
        lines.extend(_unreviewed_block(item) for item in merged["unreviewed"])
        lines.append("")
    if merged["issues"]:
        lines.append("## 处理说明")
        lines.extend(f"- {issue}" for issue in merged["issues"])
        lines.append("")
    if merged["ranked"]:
        lines.append("## 提示")
        top = merged["ranked"][0]
        lines.append(f"- 优先看：{top['company']} / {top['title']}（综合分 {top['overall']}）")
    return "\n".join(lines).rstrip() + "\n"
