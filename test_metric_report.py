"""Tests for metric_report.py (Validation Architecture v3, Phase 1)."""

from metric_report import (
    build_proportion_metric, build_correlation_metric, build_continuous_metric,
    wilson_confidence_interval, MetricStatus, MetricType,
)


# ---------------------------------------------------------------------
# Proportion metrics — zero denominator must never fabricate a result
# ---------------------------------------------------------------------

def test_proportion_zero_denominator_is_not_computable():
    m = build_proportion_metric("safety_fn_rate", 0, 0)
    assert m.status == MetricStatus.NOT_COMPUTABLE
    assert m.proportion is None


def test_proportion_zero_denominator_never_fabricates_zero():
    m = build_proportion_metric("safety_fn_rate", 0, 0)
    # Explicitly not a computed 0.0 — must be NOT_COMPUTABLE, not a
    # numeric point estimate of any kind.
    assert m.status != MetricStatus.COMPUTED


def test_proportion_normal_case_computed_with_ci():
    m = build_proportion_metric("gate_agreement", 98, 100)
    assert m.status == MetricStatus.COMPUTED
    assert m.metric_type == MetricType.PROPORTION
    assert m.proportion.point_estimate == 0.98
    assert m.proportion.confidence_interval is not None
    lower, upper = m.proportion.confidence_interval
    assert lower <= 0.98 <= upper


def test_proportion_invalid_numerator_exceeds_denominator():
    m = build_proportion_metric("bad", 5, 3)
    assert m.status == MetricStatus.NOT_COMPUTABLE


def test_proportion_negative_numerator_not_computable():
    m = build_proportion_metric("bad", -1, 10)
    assert m.status == MetricStatus.NOT_COMPUTABLE


def test_proportion_perfect_score():
    m = build_proportion_metric("perfect", 10, 10)
    assert m.proportion.point_estimate == 1.0


def test_proportion_zero_numerator_nonzero_denominator_is_computable():
    m = build_proportion_metric("zero_events", 0, 50)
    assert m.status == MetricStatus.COMPUTED
    assert m.proportion.point_estimate == 0.0


# ---------------------------------------------------------------------
# Wilson confidence interval sanity
# ---------------------------------------------------------------------

def test_wilson_ci_bounds_are_within_zero_one():
    lower, upper = wilson_confidence_interval(98, 100)
    assert 0.0 <= lower <= 1.0
    assert 0.0 <= upper <= 1.0
    assert lower <= upper


def test_wilson_ci_narrower_with_larger_n():
    lower_small, upper_small = wilson_confidence_interval(9, 10)
    lower_large, upper_large = wilson_confidence_interval(900, 1000)
    assert (upper_large - lower_large) < (upper_small - lower_small)


# ---------------------------------------------------------------------
# Correlation metrics — never forced into numerator/denominator shape
# ---------------------------------------------------------------------

def test_correlation_zero_pairs_not_computable():
    m = build_correlation_metric("pairwise_agreement", None, 0, "pairwise_agreement")
    assert m.status == MetricStatus.NOT_COMPUTABLE
    assert m.proportion is None  # never coerced into a proportion shape


def test_correlation_normal_case():
    m = build_correlation_metric("spearman", 0.72, 15, "spearman")
    assert m.status == MetricStatus.COMPUTED
    assert m.metric_type == MetricType.CORRELATION
    assert m.correlation.coefficient == 0.72
    assert m.correlation.n_pairs == 15
    assert m.correlation.method == "spearman"


def test_correlation_none_coefficient_not_computable():
    m = build_correlation_metric("spearman", None, 5, "spearman")
    assert m.status == MetricStatus.NOT_COMPUTABLE


# ---------------------------------------------------------------------
# Continuous metrics
# ---------------------------------------------------------------------

def test_continuous_empty_values_not_computable():
    m = build_continuous_metric("some_metric", [])
    assert m.status == MetricStatus.NOT_COMPUTABLE


def test_continuous_computes_mean_and_median():
    m = build_continuous_metric("some_metric", [1.0, 2.0, 3.0, 4.0])
    assert m.status == MetricStatus.COMPUTED
    assert m.continuous.mean == 2.5
    assert m.continuous.median == 2.5
    assert m.continuous.n == 4


def test_continuous_odd_length_median():
    m = build_continuous_metric("some_metric", [1.0, 2.0, 3.0])
    assert m.continuous.median == 2.0


# ---------------------------------------------------------------------
# Diversity breakdown always present (even if empty)
# ---------------------------------------------------------------------

def test_diversity_breakdown_defaults_to_empty_dicts():
    m = build_proportion_metric("m", 5, 10)
    assert m.diversity_breakdown.by_taxon == {}
    assert m.diversity_breakdown.by_indication == {}
    assert m.diversity_breakdown.by_preparation == {}
    assert m.diversity_breakdown.by_source_document == {}
