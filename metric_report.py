"""
Validation Architecture v3 — Phase 1: MetricReport.

WHAT CHANGED FROM v2 (v3 correction #9)
v2's design assumed every metric has a numerator/denominator shape.
That is true for proportions (eligibility accuracy, gate-level
agreement, false-negative rate) but not for correlation metrics
(Spearman, pairwise agreement) or continuous metrics — forcing those
into a numerator/denominator shape would misrepresent what they
measure. This module makes MetricReport explicitly metric-type aware:
a PROPORTION report carries numerator/denominator/CI, a CORRELATION
report carries a coefficient and pair count, a CONTINUOUS report
carries a value distribution summary. Each type is a separate,
optional payload on MetricReport — never forced into one shape.

ZERO DENOMINATOR (v3 correction #9)
A proportion metric with denominator == 0 NEVER produces a fabricated
0.0 or 1.0 — it produces status=NOT_COMPUTABLE with no point_estimate
and no confidence interval. This mirrors this platform's existing
"an implausible/absent value is a data gap, not a real data point"
convention (see grade_certainty_classifier.py, evidence_hierarchy_classifier.py
for the same principle applied elsewhere).

CONFIDENCE INTERVAL METHOD
Wilson score interval — chosen over the simpler normal-approximation
interval because it stays well-behaved at small n and at proportions
near 0 or 1, both of which are expected in a Gold Set (e.g. a
Safety-Serious false-negative rate is expected to have a TRUE value
of exactly 0).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MetricType(str, Enum):
    PROPORTION = "Proportion"
    CORRELATION = "Correlation"
    CONTINUOUS = "Continuous"


class MetricStatus(str, Enum):
    COMPUTED = "Computed"
    NOT_COMPUTABLE = "Not computable"


def wilson_confidence_interval(numerator: int, denominator: int, z: float = 1.96):
    """95% Wilson score interval by default (z=1.96). Returns
    (lower, upper) as floats in [0, 1]. Caller must not call this with
    denominator == 0 — see build_proportion_metric() below, which
    guards this."""
    n = denominator
    p_hat = numerator / n
    denom = 1 + z ** 2 / n
    center = (p_hat + z ** 2 / (2 * n)) / denom
    margin = (z * math.sqrt((p_hat * (1 - p_hat) / n) + (z ** 2 / (4 * n ** 2)))) / denom
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return (lower, upper)


@dataclass
class ProportionMetric:
    numerator: int
    denominator: int
    point_estimate: Optional[float] = None
    confidence_interval: Optional[tuple] = None


@dataclass
class CorrelationMetric:
    coefficient: Optional[float]
    n_pairs: int
    method: str  # e.g. "spearman" | "pairwise_agreement" | "top_k_inclusion"


@dataclass
class ContinuousMetric:
    n: int
    mean: Optional[float] = None
    median: Optional[float] = None
    values: list = field(default_factory=list)


@dataclass
class DiversityBreakdown:
    by_taxon: dict = field(default_factory=dict)
    by_indication: dict = field(default_factory=dict)
    by_preparation: dict = field(default_factory=dict)
    by_source_document: dict = field(default_factory=dict)


@dataclass
class MetricReport:
    metric_name: str
    metric_type: MetricType
    status: MetricStatus
    proportion: Optional[ProportionMetric] = None
    correlation: Optional[CorrelationMetric] = None
    continuous: Optional[ContinuousMetric] = None
    diversity_breakdown: DiversityBreakdown = field(default_factory=DiversityBreakdown)
    detail: str = ""


def build_proportion_metric(metric_name: str, numerator: int, denominator: int, detail: str = "") -> MetricReport:
    """The ONE way a proportion-shaped MetricReport should be built —
    guards the zero-denominator case explicitly (v3 correction #9)."""
    if denominator == 0:
        return MetricReport(
            metric_name=metric_name,
            metric_type=MetricType.PROPORTION,
            status=MetricStatus.NOT_COMPUTABLE,
            detail=detail or "Denominator is zero — no eligible cases for this metric.",
        )
    if numerator < 0 or numerator > denominator:
        return MetricReport(
            metric_name=metric_name,
            metric_type=MetricType.PROPORTION,
            status=MetricStatus.NOT_COMPUTABLE,
            detail=f"Invalid numerator {numerator} for denominator {denominator}.",
        )
    point_estimate = numerator / denominator
    ci = wilson_confidence_interval(numerator, denominator)
    return MetricReport(
        metric_name=metric_name,
        metric_type=MetricType.PROPORTION,
        status=MetricStatus.COMPUTED,
        proportion=ProportionMetric(
            numerator=numerator, denominator=denominator,
            point_estimate=point_estimate, confidence_interval=ci,
        ),
        detail=detail,
    )


def build_correlation_metric(metric_name: str, coefficient: Optional[float], n_pairs: int, method: str, detail: str = "") -> MetricReport:
    """Correlation/agreement-shaped metrics (Spearman, pairwise
    agreement, Top-k inclusion) — never forced into a numerator/
    denominator shape (v3 correction #6 from the prior revision, #9
    here). n_pairs == 0 also produces NOT_COMPUTABLE, for the same
    reason a zero denominator does for proportions."""
    if n_pairs == 0 or coefficient is None:
        return MetricReport(
            metric_name=metric_name,
            metric_type=MetricType.CORRELATION,
            status=MetricStatus.NOT_COMPUTABLE,
            detail=detail or "No eligible pairs for this metric.",
        )
    return MetricReport(
        metric_name=metric_name,
        metric_type=MetricType.CORRELATION,
        status=MetricStatus.COMPUTED,
        correlation=CorrelationMetric(coefficient=coefficient, n_pairs=n_pairs, method=method),
        detail=detail,
    )


def build_continuous_metric(metric_name: str, values: list, detail: str = "") -> MetricReport:
    if not values:
        return MetricReport(
            metric_name=metric_name,
            metric_type=MetricType.CONTINUOUS,
            status=MetricStatus.NOT_COMPUTABLE,
            detail=detail or "No values for this metric.",
        )
    sorted_values = sorted(values)
    n = len(sorted_values)
    mean = sum(sorted_values) / n
    median = (
        sorted_values[n // 2] if n % 2 == 1
        else (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
    )
    return MetricReport(
        metric_name=metric_name,
        metric_type=MetricType.CONTINUOUS,
        status=MetricStatus.COMPUTED,
        continuous=ContinuousMetric(n=n, mean=mean, median=median, values=list(values)),
        detail=detail,
    )
