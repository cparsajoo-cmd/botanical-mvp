"""Tests for reference_precedence.py (Validation Architecture v3, Phase 1).

Covers: five independent domain hierarchies (v3 correction #1),
precautionary safety precedence applied only among already-applicable
references (explicit requirement in the approval message), and all
five ResolutionStatus values.
"""

from applicability_check import ReferenceDomain, check_applicability
from reference_descriptor import ReferenceDescriptor
from reference_precedence import (
    resolve_precedence, ReferenceVerdict, ResolutionStatus,
)
from validation_unit import ValidationUnit


def _ref(reference_id, source_type, **overrides):
    defaults = dict(reference_id=reference_id, source_type=source_type, version="v1")
    defaults.update(overrides)
    return ReferenceDescriptor(**defaults)


def _verdict(reference_id, **overrides):
    defaults = dict(reference_id=reference_id)
    defaults.update(overrides)
    return ReferenceVerdict(**defaults)


# ---------------------------------------------------------------------
# NO_APPLICABLE_REFERENCE
# ---------------------------------------------------------------------

def test_empty_applicable_list_returns_no_applicable_reference():
    resolution = resolve_precedence(ReferenceDomain.SAFETY, [])
    assert resolution.status == ResolutionStatus.NO_APPLICABLE_REFERENCE
    assert resolution.selected_reference_id is None


# ---------------------------------------------------------------------
# SELECTED — single applicable reference
# ---------------------------------------------------------------------

def test_single_applicable_reference_is_selected_safety():
    ref = _ref("r1", "EMA_HMPC")
    verdict = _verdict("r1", safety_severity="MODERATE")
    resolution = resolve_precedence(ReferenceDomain.SAFETY, [(ref, verdict)])
    assert resolution.status == ResolutionStatus.SELECTED
    assert resolution.selected_reference_id == "r1"


def test_single_applicable_reference_is_selected_non_safety():
    ref = _ref("r1", "EMA_HMPC")
    verdict = _verdict("r1", verdict_value="supports")
    resolution = resolve_precedence(ReferenceDomain.INDICATION_EVIDENCE, [(ref, verdict)])
    assert resolution.status == ResolutionStatus.SELECTED
    assert resolution.selected_reference_id == "r1"


# ---------------------------------------------------------------------
# Domain-specific hierarchies — v3 correction #1: pharmacopoeia must
# NOT automatically outrank evidence sources for indication validation.
# ---------------------------------------------------------------------

def test_pharmacopoeia_outranks_who_for_identity_quality():
    ref_a = _ref("pharma", "PHARMACOPOEIA")
    ref_b = _ref("who", "WHO_MONOGRAPH")
    v_a = _verdict("pharma", verdict_value="X")
    v_b = _verdict("who", verdict_value="Y")
    resolution = resolve_precedence(
        ReferenceDomain.IDENTITY_QUALITY, [(ref_a, v_a), (ref_b, v_b)],
    )
    assert resolution.status == ResolutionStatus.SELECTED
    assert resolution.selected_reference_id == "pharma"


def test_pharmacopoeia_does_not_outrank_systematic_review_for_indication_evidence():
    # The exact regression this test locks: pharmacopoeia is NOT even
    # in the INDICATION_EVIDENCE hierarchy at all in Phase 1's design.
    ref_a = _ref("pharma", "PHARMACOPOEIA")
    ref_b = _ref("sr", "SYSTEMATIC_REVIEW")
    v_a = _verdict("pharma", verdict_value="X")
    v_b = _verdict("sr", verdict_value="Y")
    resolution = resolve_precedence(
        ReferenceDomain.INDICATION_EVIDENCE, [(ref_a, v_a), (ref_b, v_b)],
    )
    # PHARMACOPOEIA is not in this domain's hierarchy at all -> INSUFFICIENT_METADATA,
    # never silently ranked as if it belonged there.
    assert resolution.status == ResolutionStatus.INSUFFICIENT_METADATA


def test_systematic_review_outranks_ema_hmpc_for_indication_evidence():
    ref_a = _ref("sr", "SYSTEMATIC_REVIEW")
    ref_b = _ref("hmpc", "EMA_HMPC")
    v_a = _verdict("sr", verdict_value="X")
    v_b = _verdict("hmpc", verdict_value="Y")
    resolution = resolve_precedence(
        ReferenceDomain.INDICATION_EVIDENCE, [(ref_a, v_a), (ref_b, v_b)],
    )
    assert resolution.selected_reference_id == "sr"


def test_national_regulatory_outranks_ema_hmpc_for_regulatory_status():
    ref_a = _ref("national", "NATIONAL_REGULATORY")
    ref_b = _ref("hmpc", "EMA_HMPC")
    v_a = _verdict("national", verdict_value="X")
    v_b = _verdict("hmpc", verdict_value="Y")
    resolution = resolve_precedence(
        ReferenceDomain.REGULATORY_STATUS, [(ref_a, v_a), (ref_b, v_b)],
    )
    assert resolution.selected_reference_id == "national"


def test_ema_hmpc_outranks_pharmacopoeia_for_preparation_spec():
    ref_a = _ref("hmpc", "EMA_HMPC")
    ref_b = _ref("pharma", "PHARMACOPOEIA")
    v_a = _verdict("hmpc", verdict_value="X")
    v_b = _verdict("pharma", verdict_value="Y")
    resolution = resolve_precedence(
        ReferenceDomain.PREPARATION_SPEC, [(ref_a, v_a), (ref_b, v_b)],
    )
    assert resolution.selected_reference_id == "hmpc"


def test_unrecognized_source_type_gives_insufficient_metadata():
    ref = _ref("mystery", "SOME_UNKNOWN_SOURCE_TYPE")
    verdict = _verdict("mystery", verdict_value="X")
    resolution = resolve_precedence(ReferenceDomain.INDICATION_EVIDENCE, [(ref, verdict)])
    assert resolution.status == ResolutionStatus.INSUFFICIENT_METADATA


# ---------------------------------------------------------------------
# REFERENCE_CONFLICT — equally-ranked, disagreeing, non-safety
# ---------------------------------------------------------------------

def test_equally_ranked_disagreeing_references_give_reference_conflict():
    ref_a = _ref("who_a", "WHO_MONOGRAPH")
    ref_b = _ref("who_b", "WHO_MONOGRAPH")
    v_a = _verdict("who_a", verdict_value="supports")
    v_b = _verdict("who_b", verdict_value="does_not_support")
    resolution = resolve_precedence(
        ReferenceDomain.INDICATION_EVIDENCE, [(ref_a, v_a), (ref_b, v_b)],
    )
    assert resolution.status == ResolutionStatus.REFERENCE_CONFLICT
    assert set(resolution.conflicting_reference_ids) == {"who_a", "who_b"}


def test_equally_ranked_agreeing_references_are_selected_not_conflicted():
    ref_a = _ref("who_a", "WHO_MONOGRAPH")
    ref_b = _ref("who_b", "WHO_MONOGRAPH")
    v_a = _verdict("who_a", verdict_value="supports")
    v_b = _verdict("who_b", verdict_value="supports")
    resolution = resolve_precedence(
        ReferenceDomain.INDICATION_EVIDENCE, [(ref_a, v_a), (ref_b, v_b)],
    )
    assert resolution.status == ResolutionStatus.SELECTED


def test_never_averages_conflicting_verdicts():
    # Hard rule from Validation Architecture v2, preserved: conflicting
    # results are reported, never merged into a blended answer.
    ref_a = _ref("who_a", "WHO_MONOGRAPH")
    ref_b = _ref("who_b", "WHO_MONOGRAPH")
    v_a = _verdict("who_a", verdict_value="supports")
    v_b = _verdict("who_b", verdict_value="does_not_support")
    resolution = resolve_precedence(
        ReferenceDomain.INDICATION_EVIDENCE, [(ref_a, v_a), (ref_b, v_b)],
    )
    assert resolution.selected_reference_id is None
    assert not hasattr(resolution, "blended_verdict")


# ---------------------------------------------------------------------
# SAFETY domain — precautionary precedence (most severe wins, rank irrelevant)
# ---------------------------------------------------------------------

def test_safety_most_severe_wins_regardless_of_rank():
    # ESCOP (lower rank) has SERIOUS severity; EMA_HMPC (higher rank)
    # has only MINOR — the more severe one must win despite the lower rank.
    ref_low_rank_serious = _ref("escop", "ESCOP_MONOGRAPH")
    ref_high_rank_minor = _ref("hmpc", "EMA_HMPC")
    v_serious = _verdict("escop", safety_severity="SERIOUS", verdict_value="contraindicated")
    v_minor = _verdict("hmpc", safety_severity="MINOR", verdict_value="caution")
    resolution = resolve_precedence(
        ReferenceDomain.SAFETY, [(ref_low_rank_serious, v_serious), (ref_high_rank_minor, v_minor)],
    )
    assert resolution.status == ResolutionStatus.SELECTED
    assert resolution.selected_reference_id == "escop"


def test_safety_insufficient_metadata_when_severity_missing():
    ref = _ref("r1", "EMA_HMPC")
    verdict = _verdict("r1", safety_severity=None)
    resolution = resolve_precedence(ReferenceDomain.SAFETY, [(ref, verdict)])
    assert resolution.status == ResolutionStatus.INSUFFICIENT_METADATA


def test_safety_tied_severity_agreeing_verdicts_resolved_by_fallback_rank():
    ref_a = _ref("hmpc", "EMA_HMPC")
    ref_b = _ref("who", "WHO_MONOGRAPH")
    v_a = _verdict("hmpc", safety_severity="SERIOUS", verdict_value="contraindicated")
    v_b = _verdict("who", safety_severity="SERIOUS", verdict_value="contraindicated")
    resolution = resolve_precedence(ReferenceDomain.SAFETY, [(ref_a, v_a), (ref_b, v_b)])
    assert resolution.status == ResolutionStatus.SELECTED
    assert resolution.selected_reference_id == "hmpc"  # EMA_HMPC first in fallback rank


def test_safety_tied_severity_disagreeing_verdicts_forces_human_review():
    ref_a = _ref("r1", "NATIONAL_REGULATORY")
    ref_b = _ref("r2", "OTHER_NATIONAL_REGULATORY")
    v_a = _verdict("r1", safety_severity="SERIOUS", verdict_value="contraindicated")
    v_b = _verdict("r2", safety_severity="SERIOUS", verdict_value="caution_only")
    resolution = resolve_precedence(ReferenceDomain.SAFETY, [(ref_a, v_a), (ref_b, v_b)])
    assert resolution.status == ResolutionStatus.HUMAN_REVIEW_REQUIRED
    assert set(resolution.conflicting_reference_ids) == {"r1", "r2"}


def test_human_review_required_is_distinct_from_reference_conflict():
    # Both exist as separate statuses — safety ties escalate
    # differently from non-safety ties, per the approved policy.
    assert ResolutionStatus.HUMAN_REVIEW_REQUIRED != ResolutionStatus.REFERENCE_CONFLICT


# ---------------------------------------------------------------------
# Integration: precautionary safety precedence applied ONLY after
# applicability — the exact requirement stated in the approval message.
# ---------------------------------------------------------------------

def test_precautionary_safety_only_applies_among_already_applicable_references():
    unit = ValidationUnit(
        taxon="Valeriana officinalis L.", plant_part="root",
        population="Adults", jurisdiction="Germany", indication="Sleep",
    )
    # ref_inapplicable has a MORE severe verdict but wrong plant_part —
    # must never be allowed to win just by being more severe.
    ref_inapplicable = ReferenceDescriptor(reference_id="wrong_part", source_type="EMA_HMPC", version="v1", plant_part="leaf")
    ref_applicable = ReferenceDescriptor(reference_id="right_part", source_type="ESCOP_MONOGRAPH", version="v1", plant_part="root")

    a_inapplicable = check_applicability(ref_inapplicable, unit, ReferenceDomain.SAFETY)
    a_applicable = check_applicability(ref_applicable, unit, ReferenceDomain.SAFETY)
    assert a_inapplicable.applicable is False
    assert a_applicable.applicable is True

    v_inapplicable = _verdict("wrong_part", safety_severity="SERIOUS", verdict_value="contraindicated")
    v_applicable = _verdict("right_part", safety_severity="MINOR", verdict_value="caution")

    # Only the applicable one is passed to precedence — this is the
    # caller's responsibility (v3 correction #6), simulated here.
    filtered = [
        (ref, verdict) for ref, applicability, verdict in
        [(ref_inapplicable, a_inapplicable, v_inapplicable), (ref_applicable, a_applicable, v_applicable)]
        if applicability.applicable
    ]
    resolution = resolve_precedence(ReferenceDomain.SAFETY, filtered)
    assert resolution.status == ResolutionStatus.SELECTED
    assert resolution.selected_reference_id == "right_part"
