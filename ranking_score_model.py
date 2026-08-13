"""Pure ranking-score mechanics shared by production, sensitivity and calibration.

This module never interprets evidence and never changes eligibility, safety,
regulatory, preparation or retrieval gates. It only maps already-computed
section contributions onto an explicit weight vector.

The baseline mapping is identity-preserving: with the current active weights,
all scores are numerically identical to the pre-Phase-7 implementation.
"""
from __future__ import annotations

from collections.abc import Mapping

from phase5_scoring_config import (
    RANKING_COMPONENT_BASE_WEIGHTS,
    RANKING_COMPONENT_ACTIVE_WEIGHTS,
)


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Return a validated 100-point weight vector over the canonical sections."""
    keys = set(RANKING_COMPONENT_BASE_WEIGHTS)
    if set(weights) != keys:
        missing = sorted(keys - set(weights))
        extra = sorted(set(weights) - keys)
        raise ValueError(f"weight keys mismatch; missing={missing}, extra={extra}")
    cleaned = {k: float(weights[k]) for k in RANKING_COMPONENT_BASE_WEIGHTS}
    if any(v <= 0 for v in cleaned.values()):
        raise ValueError("all ranking weights must be > 0")
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("ranking weight total must be positive")
    return {k: v * 100.0 / total for k, v in cleaned.items()}


def reweight_score_breakdown(
    raw_breakdown: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Convert baseline-scale component points to weighted contributions.

    ``raw_breakdown`` values are component points on their historical maxima
    (35/30/5/10/15/5). A component utility is therefore raw/base_max. Applying
    the baseline weights exactly reproduces the original contribution; applying
    another normalized weight vector changes ONLY prioritization weights.
    """
    active = normalize_weights(weights or RANKING_COMPONENT_ACTIVE_WEIGHTS)
    result: dict[str, float] = {}
    for name, base_max in RANKING_COMPONENT_BASE_WEIGHTS.items():
        raw = float(raw_breakdown.get(name, 0.0) or 0.0)
        utility = raw / float(base_max)
        result[name] = utility * active[name]
    return result


def score_from_breakdown(
    raw_breakdown: Mapping[str, float],
    weights: Mapping[str, float] | None = None,
) -> float:
    """Return the [0,100] opportunity score under ``weights``."""
    weighted = reweight_score_breakdown(raw_breakdown, weights=weights)
    return round(max(0.0, min(100.0, sum(weighted.values()))), 1)
