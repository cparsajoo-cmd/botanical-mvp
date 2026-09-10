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
    INSUFFICIENT_DIRECTION_DATA,
)


def classify_evidence_consistency(profile: Mapping[str, int]) -> str:
    """Classify an outcome-count profile into one of:
    CONSISTENT_POSITIVE, MOSTLY_POSITIVE, MIXED, MOSTLY_NULL,
    CONSISTENT_NULL, MOSTLY_NEGATIVE, INSUFFICIENT, INSUFFICIENT_DIRECTION_DATA.

    `profile` is expected to carry integer counts under the keys
    "positive", "null", "harmful", "mixed", "unreported", plus an
    optional explicit "total".  This is the same shape
    candidate_shortlisting._outcome_profile() produces, restricted by the
    caller to one candidate's primary tier only (this function has no tier
    awareness of its own; tier precedence is the caller's responsibility,
    per addendum §1.3).

    DEFECT 1 FIX (pre-investor reliability repair): "unreported" records --
    evidence whose result direction was never extracted/resolved -- are
    counted toward `total` (so they are never silently discarded and the
    ValueError completeness check below still holds), but are EXCLUDED from
    the positive/negative ratio denominators. "Direction not reported" is
    missing information, not contradictory efficacy evidence, and must
    neither manufacture a MIXED classification by diluting the ratios, nor
    receive positive-direction credit by default (never counted as
    "positive"). If a tier has no evidence at all with a resolved
    direction, that is reported as the distinct INSUFFICIENT_DIRECTION_DATA
    state rather than MIXED or INSUFFICIENT (which means no evidence at
    all -- see classify_evidence_consistency({"total": 0})).

    Deterministic, ratio-based (never a raw count comparison), so
    accumulating more same-direction evidence within a tier cannot by
    itself manufacture a stronger classification once the ratio has
    stabilized, and a single study can never reach a CONSISTENT_* label
    (requires known_direction_total >= 2 -- agreement with nothing is not
    agreement).
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

    # Ratios are computed only over records with a KNOWN result direction.
    # "unreported" stays in `total` (nothing is discarded) but is removed
    # from the denominator used for classification -- see defect-1 note above.
    known_direction_total = positive + null_ + harmful + mixed
    if known_direction_total == 0:
        # Evidence exists in this tier (total > 0), but none of it has a
        # resolved outcome direction: an honest "we don't know" state,
        # never MIXED and never a positive default.
        return INSUFFICIENT_DIRECTION_DATA

    positive_ratio = positive / known_direction_total
    negative_ratio = (harmful + null_) / known_direction_total

    # A genuine positive-vs-harmful conflict within the same tier is
    # always MIXED, regardless of ratios either side.
    if harmful > 0 and positive > 0:
        return MIXED

    if positive_ratio >= 0.8 and known_direction_total >= 2:
        return CONSISTENT_POSITIVE
    if positive_ratio >= 0.5:
        return MOSTLY_POSITIVE
    if negative_ratio >= 0.8 and harmful == 0 and known_direction_total >= 2:
        return CONSISTENT_NULL
    if negative_ratio >= 0.8 and harmful > 0:
        return MOSTLY_NEGATIVE
    if negative_ratio >= 0.5:
        return MOSTLY_NULL
    # Catch-all: a pool with a genuine "mixed"-category record, or no clear
    # majority among known-direction records -- evidence exists and has a
    # resolved direction, but it does not establish a clear consistent
    # direction. Never reached merely because unreported records are
    # present (those are now excluded from known_direction_total above).
    return MIXED


def direction_data_completeness(profile: Mapping[str, int]) -> str:
    """Separate, explicit direction-data-completeness signal (defect 1,
    requirement D). "PARTIAL" whenever the tier contains at least one
    record whose direction was never resolved, alongside at least one
    record whose direction IS known -- i.e. the classification above was
    computed on a subset of the tier's records. "COMPLETE" when every
    record in the tier has a known direction (including the trivial empty
    case). Purely informational; never consumed by classify_evidence_
    consistency() and never itself alters a score or factor.
    """
    unreported = int(profile.get("unreported", 0) or 0)
    if unreported <= 0:
        return "COMPLETE"
    return "PARTIAL"
