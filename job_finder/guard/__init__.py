"""Integrity gate for third-party job postings.

A posting is untrusted text that ends up in front of an LLM next to the
candidate's profile. The "treat it as data" instruction is only as strong as the
model's adherence, so this module makes the common payload classes visible
deterministically: hidden HTML, invisible characters, and instruction-shaped
phrases in English, Japanese and Chinese. The approach follows the integrity
gate in ai-job-search (MIT, https://github.com/ai-job-search-dev/ai-job-search),
reimplemented here on ``html.parser`` with CJK patterns added.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import List, Tuple

from .html_text import extract_html, fold_block_text
from .invisible import strip_invisible
from .patterns import find_instructions, normalise_for_scan

MAX_INPUT_CHARS = 200_000
HIDDEN_TEXT_MIN_CHARS = 40
VERDICT_MAX_CHARS = 240
EXCERPT_MAX_CHARS = 120

_HTML_HINT = re.compile(r"<\s*/?[a-zA-Z!]")
_ESCAPED_HTML = re.compile(r"&lt;\s*/?[a-zA-Z]")
# Markup that survived one parse as literal text (it was entity-escaped) and carries a hiding attribute.
_ESCAPED_HIDING_TAG = re.compile(r"<\s*[a-zA-Z][^>]{0,300}?\b(?:style|hidden)\b", re.I)

_LABELS = {
    "instruction": "疑似指令",
    "hidden_content": "隐藏内容",
    "invisible_chars": "不可见字符",
    "invisible_text": "不可见文本",
}


@dataclass(frozen=True)
class Finding:
    kind: str
    excerpt: str


@dataclass(frozen=True)
class GuardResult:
    text: str
    findings: Tuple[Finding, ...] = ()

    @property
    def flagged(self) -> bool:
        return bool(self.findings)

    @property
    def verdict(self) -> str:
        if not self.findings:
            return "clean"
        parts = [f"{_LABELS[f.kind]}: {f.excerpt}" for f in self.findings]
        line = f"⚠ 检测到 {len(parts)} 项异常 | " + " | ".join(parts)
        if len(line) > VERDICT_MAX_CHARS:
            line = line[:VERDICT_MAX_CHARS - 1] + "…"
        return line


def _short(text: str) -> str:
    return normalise_for_scan(text).strip()[:EXCERPT_MAX_CHARS]


def _instruction_findings(text: str, source: str) -> List[Finding]:
    prefix = f"[{source}] " if source else ""
    return [Finding("instruction", prefix + _short(e)) for e in find_instructions(text)]


def _to_visible_text(cleaned: str) -> Tuple[str, List[str], List[str]]:
    if _ESCAPED_HTML.search(cleaned) and not _HTML_HINT.search(cleaned):
        cleaned = html.unescape(cleaned)  # JSON APIs often ship escaped HTML
    if not _HTML_HINT.search(cleaned):
        text = re.sub(r"[ \t\xa0\f\v]+", " ", cleaned.replace("\r\n", "\n"))
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip(), [], []
    parsed = extract_html(cleaned)
    visible, hidden, dropped = parsed.visible, list(parsed.hidden), list(parsed.dropped)
    if _ESCAPED_HIDING_TAG.search(visible):
        again = extract_html(visible)  # one extra pass only, so nesting cannot loop
        visible = again.visible
        hidden += again.hidden
        dropped += again.dropped
    return fold_block_text(visible), hidden, dropped


def _as_text(raw: object) -> str:
    if isinstance(raw, str):
        return raw[:MAX_INPUT_CHARS]
    if isinstance(raw, bytes):
        return raw[:MAX_INPUT_CHARS].decode("utf-8", errors="replace")
    return ""  # None, numbers, lists and dicts are not posting bodies


def guard(raw: object) -> GuardResult:
    """Clean ``raw`` into visible text and report anything suspicious about it."""
    scan = strip_invisible(_as_text(raw))
    text, hidden, dropped = _to_visible_text(scan.text)

    findings: List[Finding] = []
    if scan.flagged:
        findings.append(Finding("invisible_chars", f"{scan.flagged} 个零宽/双向控制/标签字符"))
    for payload in scan.decoded:
        findings.append(Finding("invisible_text", _short(payload)))
        findings.extend(_instruction_findings(payload, "不可见文本"))

    findings.extend(_instruction_findings(text, ""))
    if scan.flagged:
        # A zero-width character used as a word separator glues the phrase together.
        spaced_text, _, _ = _to_visible_text(scan.spaced)
        findings.extend(_instruction_findings(spaced_text, ""))
    for block in hidden:
        if len(block.strip()) >= HIDDEN_TEXT_MIN_CHARS:
            findings.append(Finding("hidden_content", _short(block)))
        findings.extend(_instruction_findings(block, "隐藏"))
    for block in dropped:
        findings.extend(_instruction_findings(block, "注释/脚本"))

    return GuardResult(text=text, findings=tuple(dict.fromkeys(findings)))


__all__ = ["guard", "GuardResult", "Finding"]
