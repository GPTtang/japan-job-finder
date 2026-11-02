"""Instruction-shaped phrases aimed at an AI agent rather than a human reader.

Kept deliberately narrow: job ads for LLM roles legitimately say "system prompt",
"prompt engineering" or "SSH", so every pattern needs a verb/object pairing.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List

_FLAGS = re.IGNORECASE

_ENGLISH = (
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+|my\s+)?"
    r"(?:previous|prior|above|earlier|preceding|initial|original|system)\s+(?:instructions?|prompts?)",
    r"\byou\s+are\s+(?:now\s+)?(?:an?|the)\s+(?:ai\s+(?:assistant|agent|model)|chatbot|helpful\s+assistant)\b",
    r"\b(?:reveal|print|show|output|repeat|display|leak|disclose)\s+(?:me\s+)?"
    r"(?:your\s+(?:system\s+prompt|instructions|prompt)|the\s+system\s+prompt|"
    r"(?:your|the)\s+hidden\s+(?:prompt|instructions?))\b",
    r"\b(?:do\s+not|don'?t|never)\s+(?:tell|inform|notify)\s+the\s+user\b(?!['\u2019]s)",
    r"\b(?:do\s+not|don'?t|never)\s+(?:mention|reveal|disclose)\s+(?:this|these|that|it)\b"
    r"[^.\n]{0,30}\bto\s+the\s+user\b",
    r"\b(?:run|execute)\s+the\s+following\s+(?:commands?|scripts?|shell)\b",
    r"\b(?:curl|wget)\b[^\n|]{0,100}\|\s*(?:ba|z)?sh\b",
    r"\[/?inst\]|<\|[a-z_]+\|>|###\s*(?:system|instruction)",
)

_JA_AMOUNT = r"(?:すべて|全て|全部|完全に|一切)?"
_JAPANESE = (
    r"(?:以前|これまで|上記|前述|先ほど|それまで)の(?:指示|命令|プロンプト|ルール)を" + _JA_AMOUNT + r"(?:無視|むし|忘れ|破棄)",
    r"(?:指示|命令|ルール)を" + _JA_AMOUNT + r"(?:無視|むし)",
    r"システムプロンプト[をは]?.{0,6}(?:表示|出力|開示|教え|見せ)(?:て|してください|しなさい|せよ|しろ)",
    r"ユーザー(?:に|には)(?:は)?(?:伝え|知らせ|言わ|教え)ない",
    r"(?:以下|次)の(?:コマンド|スクリプト|コード)を(?:実行|走らせ)",
    r"あなたは(?:AI)?(?:アシスタント|エージェント|言語モデル)"
    r"(?=です|である|として(?:行動|振る舞|動作|回答|応答)|[。．.、，,!！\s]|$)",
)

_CHINESE = (
    r"(?:忽略|无视|無視|忽视|忘记).{0,8}?(?:指令|指示|提示词?|规则|命令)",
    r"不要(?:告诉|告知|通知)用户",
    r"你是(?:一个|一名)?(?:AI|人工智能|智能)(?:助手|助理|机器人)(?=[，,。.！!：:；;\s]|请|$)",
    r"(?:输出|显示|泄露|告诉我)(?:你的)?系统提示(?:词)?",
    r"(?:执行|运行)以下(?:命令(?!行)|代码|脚本)(?!的)",
)

INSTRUCTION_PATTERNS = tuple(re.compile(p, _FLAGS) for p in _ENGLISH + _JAPANESE + _CHINESE)

EXCERPT_BEFORE = 30
EXCERPT_AFTER = 50


# Cyrillic and Greek letters that are visually identical to Latin ones.
_CONFUSABLES = str.maketrans({
    **dict(zip("аеорсхуіјѕһ", "aeopcxyijsh")),
    **dict(zip("АВЕКМНОРСТХУІ", "ABEKMHOPCTXYI")),
    **dict(zip("οαινρ", "oaivp")),
    **dict(zip("ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ", "ABEZHIKMNOPTYX")),
})


def normalise_for_scan(text: str) -> str:
    """Fold full-width forms and Latin look-alikes so obfuscated phrases still match."""
    folded = unicodedata.normalize("NFKC", text).translate(_CONFUSABLES)
    return re.sub(r"\s+", " ", folded)


def find_instructions(text: str) -> List[str]:
    """Return one short excerpt per matching pattern."""
    folded = normalise_for_scan(text)
    excerpts: List[str] = []
    for pattern in INSTRUCTION_PATTERNS:
        match = pattern.search(folded)
        if match:
            start = max(0, match.start() - EXCERPT_BEFORE)
            excerpts.append(folded[start:match.end() + EXCERPT_AFTER].strip())
    return excerpts
