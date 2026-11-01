"""Detect and remove characters that render as nothing but are still read by a model."""
from __future__ import annotations

import re
from typing import NamedTuple, Tuple

_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_BIDI_BENIGN = "\u200e\u200f\u202a\u202b\u202c"
_BIDI_TAMPER = "\u202d\u202e\u2066\u2067\u2068\u2069"  # overrides and isolates
_SOFT_HYPHEN = "\u00ad"
# Default-ignorable or filler code points that render as nothing.
_OTHER_IGNORABLE = (
    "\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u2061\u2062\u2063\u2064"
    "\u2800\u3164\uffa0\ufff9\ufffa\ufffb"
)
_TAG_FIRST = 0xE0000

_REMOVABLE_CLASS = (
    re.escape(_ZERO_WIDTH + _BIDI_BENIGN + _BIDI_TAMPER + _SOFT_HYPHEN + _OTHER_IGNORABLE)
    + "\x00-\x08\x0b\x0c\x0e-\x1f\x7f"  # C0 controls other than \t \n \r
    + "\ufe00-\ufe0f\U000E0100-\U000E01EF"  # variation selectors
)
_REMOVABLE_RUN = re.compile(f"[{_REMOVABLE_CLASS}]+")

_ALWAYS_FLAGGED = set(_BIDI_TAMPER) | {chr(c) for c in range(0xE0100, 0xE01F0)}
_NEVER_FLAGGED = set(_SOFT_HYPHEN + _BIDI_BENIGN)

_TAG_RUN = re.compile("[\U000E0000-\U000E007F]+")
# Subdivision flag emoji (e.g. England) legitimately use tag characters.
_FLAG_SEQUENCE = re.compile("\U0001F3F4[\U000E0020-\U000E007E]+\U000E007F")
# A typographic space wedged between two Latin letters splits a word; nothing legitimate does that.
_IN_WORD_SPACE = re.compile(r"(?<=[A-Za-z])[\u1680\u2000-\u200a\u202f\u205f\u3000](?=[A-Za-z])")


class InvisibleScan(NamedTuple):
    text: str     # invisible characters removed
    spaced: str   # the same, with each run replaced by a space (for phrase scanning)
    flagged: int  # characters that indicate tampering
    decoded: Tuple[str, ...]  # text spelled in Unicode tag characters


def _decode_tag_run(run: str) -> str:
    chars = (chr(ord(c) - _TAG_FIRST) for c in run)
    return "".join(c for c in chars if " " <= c < "\x7f")


def _count_tampering(text: str) -> int:
    flagged = 0
    for run in _REMOVABLE_RUN.finditer(text):
        chars = run.group()
        flagged += sum(1 for c in chars if c in _ALWAYS_FLAGGED)
        rest = sum(1 for c in chars if c not in _ALWAYS_FLAGGED and c not in _NEVER_FLAGGED)
        before = text[run.start() - 1] if run.start() else ""
        after = text[run.end()] if run.end() < len(text) else ""
        if rest and before.isalpha() and after.isalpha():
            flagged += rest
    return flagged


def strip_invisible(text: str) -> InvisibleScan:
    """Return ``text`` without invisible characters, plus what they were hiding."""
    text = _FLAG_SEQUENCE.sub("\U0001F3F4", text)
    runs = _TAG_RUN.findall(text)
    decoded = tuple(d for d in (_decode_tag_run(r) for r in runs) if d.strip())
    flagged = sum(len(r) for r in runs)
    text = _TAG_RUN.sub("", text)
    flagged += len(_IN_WORD_SPACE.findall(text))
    text = _IN_WORD_SPACE.sub("", text)
    flagged += _count_tampering(text)
    cleaned = _REMOVABLE_RUN.sub("", text)
    spaced = _REMOVABLE_RUN.sub(" ", text) if flagged else cleaned
    return InvisibleScan(cleaned, spaced, flagged, decoded)
