"""The scoring rubric: weighted dimensions, hard gates and verdict bands."""
from __future__ import annotations

from typing import Mapping, Tuple

# (name, weight in percent); weights sum to 100.
DIMENSIONS: Tuple[Tuple[str, int], ...] = (
    ("technical", 30),
    ("experience", 25),
    ("language", 20),
    ("career", 25),
)

# (minimum score, label), highest first.
BANDS: Tuple[Tuple[int, str], ...] = (
    (75, "强匹配"),
    (60, "较好匹配"),
    (45, "一般匹配"),
    (30, "较弱匹配"),
    (0, "不匹配"),
)

GATES: Tuple[str, ...] = ("location", "language", "visa")
GATE_VALUES: Tuple[str, ...] = ("PASS", "FLAG", "FAIL")

_RUBRIC = """\
Score each posting 0-100 on four dimensions, from the posting text and the candidate profile only.

- technical ({technical}%): overlap between the posting's required stack and the candidate's skills; seniority fit.
- experience ({experience}%): domain and years of experience versus what the role asks for.
- language ({language}%): Japanese level versus the posting's requirement (JLPT, "business level", "native"), \
English-working-environment fit, and whether Chinese is genuinely REQUIRED or PREFERRED for the work \
(bridging with a China team, Chinese-speaking customers). An office merely located in China, or the word \
"offshore" on its own, is not a language signal. If the candidate is a native Chinese speaker, give credit only \
when the role really uses it.
- career ({career}%): fit with the roles the candidate wants and any stated deal-breakers.

Gates (independent of the scores). Use PASS, FLAG or FAIL for each:
- location: FAIL if the role needs relocation or a base the candidate excluded; FLAG for heavy travel or unclear.
- language: FAIL if the posting requires a language level far above the candidate's declared level \
(e.g. "native Japanese" for N3) or a language they do not speak; FLAG if only somewhat above.
- visa: FAIL if the posting says it will not sponsor or requires Japanese nationality/permanent residence and \
the candidate needs sponsorship; FLAG if sponsorship is unclear for a candidate who needs it; PASS otherwise.

Be honest: a poor fit gets a low score however prestigious the company. State real gaps. \
Score only from text you were given; never invent details about the company.
"""


def overall_score(scores: Mapping[str, float]) -> float:
    """Weighted average of the dimension scores, rounded to one decimal."""
    total = sum(scores[name] * weight for name, weight in DIMENSIONS)
    return round(total / 100, 1)


def band(score: float) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return BANDS[-1][1]


def render_rubric() -> str:
    return _RUBRIC.format(**dict(DIMENSIONS)) + "\nGate names: " + ", ".join(GATES) + \
        ". Gate values: " + ", ".join(GATE_VALUES) + "."
