"""Pure validation metrics for pharmaceutical safety decisions.

This module is intentionally independent from ranking/scoring.  It consumes
already-labelled validation outcomes and reports safety operating
characteristics; it never changes a production decision.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SafetyOutcome:
    serious_truth: bool
    serious_predicted: bool
    no_go_predicted: bool
    unknown_or_incomplete: bool
    expert_review_predicted: bool = False


def _ratio(n: int, d: int) -> float | None:
    return (n / d) if d else None


def compute_safety_metrics(outcomes: Iterable[SafetyOutcome]) -> dict[str, float | None]:
    rows = tuple(outcomes)
    tp = sum(r.serious_truth and r.serious_predicted for r in rows)
    fn = sum(r.serious_truth and not r.serious_predicted for r in rows)
    fp = sum((not r.serious_truth) and r.serious_predicted for r in rows)
    tn = sum((not r.serious_truth) and (not r.serious_predicted) for r in rows)
    no_go_tp = sum(r.serious_truth and r.no_go_predicted for r in rows)
    no_go_fp = sum((not r.serious_truth) and r.no_go_predicted for r in rows)
    return {
        "serious_safety_recall": _ratio(tp, tp + fn),
        "serious_safety_precision": _ratio(tp, tp + fp),
        "false_negative_rate": _ratio(fn, tp + fn),
        "false_positive_rate": _ratio(fp, fp + tn),
        "no_go_precision": _ratio(no_go_tp, no_go_tp + no_go_fp),
        "no_go_recall": _ratio(no_go_tp, tp + fn),
        "expert_review_rate": _ratio(sum(r.expert_review_predicted or r.unknown_or_incomplete for r in rows), len(rows)),
        "unknown_safety_rate": _ratio(sum(r.unknown_or_incomplete for r in rows), len(rows)),
    }
