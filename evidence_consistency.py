"""Phase 5 — Evidence Consistency classification.

A single, independent, directly-testable helper: given a de-duplicated
outcome-count profile (positive/null/harmful/mixed counts, restricted to
one candidate's PRIMARY evidence tier — see candidate_shortlisting.py's
tier-precedence logic, which computes this profile before calling here),
classify it into one of seven buckets. This module does not read
DataFrames, does not classify study design, and does not duplicate any
part of _evidence_quality()'s hierarchy logic — it only maps counts to a
label.

PROVISIONAL. NOT CLINICALLY VALIDATED. NOT STATISTICALLY CALIBRATED.
Thresholds chosen for internal consistency (ratio-based, sub-linear in
volume) per PHASE5_SCORING_CALIBRATION_AUDIT_ADDENDUM.md §2.1 — not
derived from clinical trial data.
"""
from __future__ import annotations

from typing import Mapping

from phase5_scoring_config import (
    CONSISTENT_POSITIVE,
    MOSTLY_POSITIVE,
    MIXED,
    MOSTLY_NULL,
    CONSISTENT_NULL,
    MOSTLY_NEGATIVE,
    INSUFFICIENT,
)


def classify_evidence_consistency(profile: Mapping[str, int]) -> str:
    """Classify an outcome-count profile into one of:
    CONSISTENT_POSITIVE, MOSTLY_POSITIVE, MIXED, MOSTLY_NULL,
    CONSISTENT_NULL, MOSTLY_NEGATIVE, INSUFFICIENT.

    `profile` is expected to carry integer counts under the keys
    "positive", "null", "harmful", "mixed", "unreported", plus an
    optional explicit "total".  Unreported records remain in the
    denominator: they are evidence records whose result direction is not
    established, not records that may be silently discarded.  This is the
    same shape candidate_shortlisting._outcome_profile() produces,
    restricted by the caller to one candidate's primary tier only (this
    function has no tier awareness of its own; tier precedence is the
    caller's responsibility, per addendum §1.3).

    Deterministic, ratio-based (never a raw count comparison), so
    accumulating more same-direction evidence within a tier cannot by
    itself manufacture a stronger classification once the ratio has
    stabilized, and a single study can never reach a CONSISTENT_* label
    (requires total >= 2 -- agreement with nothing is not agreement).
    """
    positive = int(profile.get("positive", 0) or 0)
    null_ = int(profile.get("null", 0) or 0)
    harmful = int(profile.get("harmful", 0) or 0)
    mixed = int(profile.get("mixed", 0) or 0)
    unreported = int(profile.get("unreported", 0) or 0)
    known_sum = positive + null_ + harmful + mixed + unreported
    explicit_total = profile.get("total", None)
    total = int(explicit_total) if explicit_total is not None else known_sum

    if total < known_sum:
        raise ValueError(
            "profile['total'] cannot be smaller than the sum of its "
            "positive/null/harmful/mixed/unreported counts"
        )

    if total == 0:
        return INSUFFICIENT

    positive_ratio = positive / total
    negative_ratio = (harmful + null_) / total

    # A genuine positive-vs-harmful conflict within the same tier is
    # always MIXED, regardless of ratios either side.
    if harmful > 0 and positive > 0:
        return MIXED

    if positive_ratio >= 0.8 and total >= 2:
        return CONSISTENT_POSITIVE
    if positive_ratio >= 0.5:
        return MOSTLY_POSITIVE
    if negative_ratio >= 0.8 and harmful == 0 and total >= 2:
        return CONSISTENT_NULL
    if negative_ratio >= 0.8 and harmful > 0:
        return MOSTLY_NEGATIVE
    if negative_ratio >= 0.5:
        return MOSTLY_NULL
    # Catch-all: e.g. a pool that is purely "mixed" or "unreported"
    # category rows — evidence exists, but it does not establish a clear
    # direction.  Such a non-empty profile is MIXED, never INSUFFICIENT and
    # never a full-credit positive default.
    return MIXED
