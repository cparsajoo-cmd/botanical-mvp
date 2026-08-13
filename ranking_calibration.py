"""Expert-calibration harness for the R&D opportunity ranking model.

This is intentionally separate from production scoring. It can EVALUATE or
SEARCH candidate weight/threshold configurations only when explicit expert
labels are supplied. It never silently writes a new production configuration.
That separation prevents a regression set, synthetic invariant set, or the
model's own outputs from being mistaken for independent expert calibration.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Iterable, Mapping

from phase5_scoring_config import (
    RANKING_COMPONENT_ACTIVE_WEIGHTS,
    RANKING_STRONG_PRIORITY_THRESHOLD,
    RANKING_CALIBRATION_STATUS,
)
from ranking_score_model import normalize_weights, score_from_breakdown


class CalibrationDataError(ValueError):
    pass


@dataclass(frozen=True)
class CalibrationResult:
    weights: dict[str, float]
    strong_threshold: float
    pairwise_agreement: float
    threshold_accuracy: float | None
    labelled_pairs: int
    labelled_threshold_cases: int
    status: str = "CANDIDATE_CONFIGURATION_ONLY_NOT_PRODUCTION"


def _labelled_pairs(benchmark: Mapping[str, Any], split: str) -> list[Mapping[str, Any]]:
    rows = []
    for item in benchmark.get("pairs", []) or []:
        if str(item.get("split", "calibration")) != split:
            continue
        if item.get("preferred") not in {"A", "B", "TIE"}:
            continue
        rows.append(item)
    return rows


def _labelled_threshold_cases(benchmark: Mapping[str, Any], split: str) -> list[Mapping[str, Any]]:
    rows = []
    for item in benchmark.get("threshold_cases", []) or []:
        if str(item.get("split", "calibration")) != split:
            continue
        if item.get("expert_priority") not in {"STRONG_PRIORITY", "INVESTIGATE"}:
            continue
        rows.append(item)
    return rows


def calibration_readiness(benchmark: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "declared_status": RANKING_CALIBRATION_STATUS,
        "calibration_pairs": len(_labelled_pairs(benchmark, "calibration")),
        "holdout_pairs": len(_labelled_pairs(benchmark, "holdout")),
        "calibration_threshold_cases": len(_labelled_threshold_cases(benchmark, "calibration")),
        "holdout_threshold_cases": len(_labelled_threshold_cases(benchmark, "holdout")),
    }


def evaluate_expert_benchmark(
    benchmark: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
    strong_threshold: float = RANKING_STRONG_PRIORITY_THRESHOLD,
    split: str = "holdout",
) -> dict[str, Any]:
    weights = normalize_weights(weights or RANKING_COMPONENT_ACTIVE_WEIGHTS)
    pairs = _labelled_pairs(benchmark, split)
    threshold_cases = _labelled_threshold_cases(benchmark, split)
    if not pairs and not threshold_cases:
        raise CalibrationDataError(f"no expert-labelled cases for split={split!r}")

    correct = 0
    pair_details = []
    for item in pairs:
        a = score_from_breakdown(item["candidate_a"]["score_breakdown"], weights)
        b = score_from_breakdown(item["candidate_b"]["score_breakdown"], weights)
        predicted = "TIE" if abs(a - b) < 1e-9 else ("A" if a > b else "B")
        expected = item["preferred"]
        correct += int(predicted == expected)
        pair_details.append({"pair_id": item.get("pair_id"), "predicted": predicted, "expected": expected, "score_a": a, "score_b": b})

    threshold_correct = 0
    threshold_details = []
    for item in threshold_cases:
        score = score_from_breakdown(item["score_breakdown"], weights)
        predicted = "STRONG_PRIORITY" if score >= float(strong_threshold) else "INVESTIGATE"
        expected = item["expert_priority"]
        threshold_correct += int(predicted == expected)
        threshold_details.append({"case_id": item.get("case_id"), "predicted": predicted, "expected": expected, "score": score})

    return {
        "split": split,
        "pairwise_agreement": (correct / len(pairs)) if pairs else None,
        "threshold_accuracy": (threshold_correct / len(threshold_cases)) if threshold_cases else None,
        "labelled_pairs": len(pairs),
        "labelled_threshold_cases": len(threshold_cases),
        "pair_details": pair_details,
        "threshold_details": threshold_details,
    }


def search_candidate_configuration(
    benchmark: Mapping[str, Any],
    *,
    multipliers: Iterable[float] = (0.8, 1.0, 1.2),
    thresholds: Iterable[float] = tuple(range(72, 85)),
) -> CalibrationResult:
    """Constrained grid search on CALIBRATION labels only.

    This produces a candidate configuration for later holdout evaluation; it
    never edits phase5_scoring_config.py. At least 5 pairwise labels are
    required so a tiny hand-picked set cannot accidentally be called a
    calibration exercise.
    """
    pairs = _labelled_pairs(benchmark, "calibration")
    t_cases = _labelled_threshold_cases(benchmark, "calibration")
    if len(pairs) < 5:
        raise CalibrationDataError("at least 5 expert-labelled calibration pairs are required")

    names = list(RANKING_COMPONENT_ACTIVE_WEIGHTS)
    base = RANKING_COMPONENT_ACTIVE_WEIGHTS
    best = None
    for combo in product(tuple(multipliers), repeat=len(names)):
        candidate = normalize_weights({name: base[name] * mult for name, mult in zip(names, combo)})
        for threshold in thresholds:
            report = evaluate_expert_benchmark(
                benchmark, weights=candidate, strong_threshold=float(threshold), split="calibration"
            )
            pair_agreement = report["pairwise_agreement"] or 0.0
            threshold_accuracy = report["threshold_accuracy"]
            threshold_term = 0.0 if threshold_accuracy is None else threshold_accuracy
            objective = pair_agreement + 0.25 * threshold_term
            # deterministic tie-breaker: prefer the smaller L1 departure from
            # current weights, then a threshold closer to the current 78.
            l1 = sum(abs(candidate[n] - base[n]) for n in names)
            tie = (-l1, -abs(float(threshold) - RANKING_STRONG_PRIORITY_THRESHOLD))
            key = (objective, pair_agreement, threshold_term, *tie)
            if best is None or key > best[0]:
                best = (key, candidate, float(threshold), report)

    assert best is not None
    _, weights, threshold, report = best
    return CalibrationResult(
        weights=dict(weights),
        strong_threshold=threshold,
        pairwise_agreement=float(report["pairwise_agreement"] or 0.0),
        threshold_accuracy=report["threshold_accuracy"],
        labelled_pairs=report["labelled_pairs"],
        labelled_threshold_cases=report["labelled_threshold_cases"],
    )
