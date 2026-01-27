from __future__ import annotations


def calc_sentence_score(
    accuracy: int,
    clarity: int,
    empathy: int,
    w_accuracy: float = 0.4,
    w_clarity: float = 0.3,
    w_empathy: float = 0.3,
) -> float:
    score = accuracy * w_accuracy + clarity * w_clarity + empathy * w_empathy
    score = max(1.0, min(5.0, float(score)))
    return round(score, 2)
