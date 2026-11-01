"""Text signals used to detect Chinese-speaker, Bridge SE and JLPT requirements."""
from __future__ import annotations

import re
from typing import Iterable

CHINESE_ADVANTAGE_SIGNALS = (
    "中国語", "chinese", "中文", "mandarin",
    "中国系", "中国人", "华人", "オフショア", "offshore",
    "bridge se", "ブリッジse", "ブリッジエンジニア",
    "大連", "上海", "北京", "深圳", "沈阳",
    "dalian", "shanghai", "beijing", "shenzhen",
)

BRIDGE_SE_SIGNALS = (
    "bridge se", "ブリッジse", "ブリッジエンジニア", "bridge engineer",
    "オフショア", "offshore", "中国語", "対中", "日中",
    "中国拠点", "中国チーム", "中国開発",
)

JLPT_REQUIREMENT_MAP = {
    "n1": "N1", "jlpt n1": "N1", "日本語n1": "N1", "n1以上": "N1",
    "native japanese": "N1", "日本語ネイティブ": "N1",
    "n2": "N2", "jlpt n2": "N2", "日本語n2": "N2", "n2以上": "N2",
    "ビジネス日本語": "N2", "business japanese": "N2",
    "n3": "N3", "jlpt n3": "N3", "n3以上": "N3",
    "日常会話": "N3", "conversational japanese": "N3",
}

JLPT_RANK = {"N1": 1, "N2": 2, "N3": 3, "N4": 4, "N5": 5, None: 99}

_ASCII_TERM = re.compile(r"[a-z0-9 .+#-]+")


def has_term(text: str, term: str) -> bool:
    """Case-insensitive containment; ASCII terms must not be embedded in a longer word.

    CJK terms have no word separators, so they match as plain substrings.
    """
    text_l = text.lower()
    term_l = term.lower()
    if not _ASCII_TERM.fullmatch(term_l):
        return term_l in text_l
    head = r"(?<![a-z0-9])" if term_l[0].isalnum() else ""
    tail = r"(?![a-z0-9])" if term_l[-1].isalnum() else ""
    return re.search(head + re.escape(term_l) + tail, text_l) is not None


def has_any_term(text: str, terms: Iterable[str]) -> bool:
    return any(has_term(text, term) for term in terms)
