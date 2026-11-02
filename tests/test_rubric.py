import pytest

from job_finder.rerank.rubric import (
    BANDS,
    DIMENSIONS,
    GATE_VALUES,
    GATES,
    band,
    overall_score,
    render_rubric,
)


def test_weights_sum_to_one_hundred():
    assert sum(weight for _, weight in DIMENSIONS) == 100


def test_overall_is_weighted_average():
    scores = {"technical": 100, "experience": 0, "language": 0, "career": 0}
    assert overall_score(scores) == 30.0
    assert overall_score({name: 80 for name, _ in DIMENSIONS}) == 80.0


def test_overall_rounds_to_one_decimal():
    scores = {"technical": 77, "experience": 66, "language": 55, "career": 44}
    assert overall_score(scores) == round((77 * 30 + 66 * 25 + 55 * 20 + 44 * 25) / 100, 1)


@pytest.mark.parametrize("score,label", [
    (100, "强匹配"), (75, "强匹配"), (74.9, "较好匹配"), (60, "较好匹配"), (59.9, "一般匹配"),
    (45, "一般匹配"), (44.9, "较弱匹配"), (30, "较弱匹配"), (29.9, "不匹配"), (0, "不匹配"),
])
def test_band_edges(score, label):
    assert band(score) == label


def test_bands_are_ordered_high_to_low():
    thresholds = [t for t, _ in BANDS]
    assert thresholds == sorted(thresholds, reverse=True) and thresholds[-1] == 0


def test_gate_vocabulary():
    assert GATES == ("location", "language", "visa") and GATE_VALUES == ("PASS", "FLAG", "FAIL")


def test_rendered_rubric_names_every_dimension_gate_and_weight():
    text = render_rubric()
    for name, weight in DIMENSIONS:
        assert name in text and str(weight) in text
    for gate in GATES:
        assert gate in text
    assert "FAIL" in text and "FLAG" in text
