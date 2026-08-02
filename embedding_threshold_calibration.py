"""Embedding-threshold calibration.

Computes precision / recall / false-positive rate / false-negative rate
over a sweep of candidate cosine-similarity thresholds, given a labeled set
of (query, record_text, is_relevant, similarity) cases.

This module does not call OpenAI or Supabase itself -- `similarity` is
supplied by the caller for each case. That is deliberate: it lets the exact
same metric-computation code run in two situations:

1. REAL calibration (production use): a caller embeds each labeled case's
   query and record text via the real OpenAI API, computes real cosine
   similarity, and passes those real values in. This has not been done in
   this environment -- see EMBEDDING_THRESHOLD_CALIBRATION.md section
   "What this document is NOT" for why (no outbound network access to
   api.openai.com from this sandbox).

2. Illustrative dry-run (what this environment CAN do): synthetic
   similarity values standing in for real embeddings, to validate the
   calibration methodology itself and produce a report of the expected
   shape -- clearly labeled as synthetic throughout.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationCase:
    label: str          # short identifier, e.g. "ginkgo_cognitive_decline_direct"
    query: str
    record_text: str
    is_relevant: bool   # ground truth: should this case be treated as relevant
    similarity: float   # cosine similarity for this (query, record_text) pair


@dataclass(frozen=True)
class ThresholdMetrics:
    threshold: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def false_positive_rate(self) -> float:
        denom = self.false_positives + self.true_negatives
        return self.false_positives / denom if denom else 0.0

    @property
    def false_negative_rate(self) -> float:
        denom = self.false_negatives + self.true_positives
        return self.false_negatives / denom if denom else 0.0


def evaluate_threshold(cases: list[CalibrationCase], threshold: float) -> ThresholdMetrics:
    tp = fp = tn = fn = 0
    for case in cases:
        predicted_relevant = case.similarity >= threshold
        if predicted_relevant and case.is_relevant:
            tp += 1
        elif predicted_relevant and not case.is_relevant:
            fp += 1
        elif not predicted_relevant and not case.is_relevant:
            tn += 1
        else:
            fn += 1
    return ThresholdMetrics(threshold, tp, fp, tn, fn)


def sweep_thresholds(
    cases: list[CalibrationCase], thresholds: list[float] | None = None,
) -> list[ThresholdMetrics]:
    thresholds = thresholds or [round(0.05 * i, 2) for i in range(1, 20)]  # 0.05..0.95
    return [evaluate_threshold(cases, t) for t in thresholds]


def best_threshold_by_f1(cases: list[CalibrationCase], thresholds: list[float] | None = None) -> ThresholdMetrics:
    """Selects the threshold maximizing F1 (precision/recall balance), not
    the one that happens to make any single example pass -- per the
    explicit instruction not to choose a threshold only because it makes
    one example pass."""
    results = sweep_thresholds(cases, thresholds)

    def _f1(m: ThresholdMetrics) -> float:
        p, r = m.precision, m.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    return max(results, key=_f1)


def format_report(cases: list[CalibrationCase], thresholds: list[float] | None = None) -> str:
    results = sweep_thresholds(cases, thresholds)
    lines = [
        f"{'threshold':>9} {'precision':>9} {'recall':>9} {'FPR':>9} {'FNR':>9} {'TP':>4} {'FP':>4} {'TN':>4} {'FN':>4}",
    ]
    for m in results:
        lines.append(
            f"{m.threshold:>9.2f} {m.precision:>9.3f} {m.recall:>9.3f} "
            f"{m.false_positive_rate:>9.3f} {m.false_negative_rate:>9.3f} "
            f"{m.true_positives:>4} {m.false_positives:>4} {m.true_negatives:>4} {m.false_negatives:>4}"
        )
    best = best_threshold_by_f1(cases, thresholds)
    lines.append(f"\nBest by F1: threshold={best.threshold:.2f} precision={best.precision:.3f} recall={best.recall:.3f}")
    return "\n".join(lines)
