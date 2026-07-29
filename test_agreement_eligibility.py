"""
Tests for agreement_eligibility.py (Prospective Claim-to-Decision
Mapping Proposal, Phases 1 & 2).

Uses minimal, synthetic, deterministic GoldCases — not the frozen
Case 001/002/003 files — none of which are touched by this file.
"""

from datetime import date

from agreement_eligibility import (
    ADOPTED_CONDITIONAL_POLICY, AgreementEligibility, AgreementIneligibilityReason,
    ConditionalMappingPolicy, ExpectedOutputDirectionConflictError,
    assess_agreement_eligibility, derive_expected_output_from_resolved_outcomes,
    map_assertion_state_to_direction,
)
from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import AssertionState, AssertionType, CurationStatus, TransformationType
from gold_case import DecisionDirection, ExpectedOutput, GoldCase, GoldCaseReference
from reference_claim import NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit


# ---------------------------------------------------------------------
# map_assertion_state_to_direction()
# ---------------------------------------------------------------------

def test_present_maps_to_positive():
    assert map_assertion_state_to_direction(AssertionState.PRESENT) == DecisionDirection.POSITIVE


def test_absent_maps_to_negative():
    assert map_assertion_state_to_direction(AssertionState.ABSENT) == DecisionDirection.NEGATIVE


def test_not_stated_never_maps():
    assert map_assertion_state_to_direction(AssertionState.NOT_STATED) is None


def test_insufficient_never_maps():
    assert map_assertion_state_to_direction(AssertionState.INSUFFICIENT) is None


def test_adopted_default_policy_is_unresolved():
    assert ADOPTED_CONDITIONAL_POLICY == ConditionalMappingPolicy.UNRESOLVED


def test_conditional_unresolved_by_default():
    assert map_assertion_state_to_direction(AssertionState.CONDITIONAL) is None


def test_conditional_maps_to_hold_under_option_b():
    result = map_assertion_state_to_direction(
        AssertionState.CONDITIONAL, conditional_policy=ConditionalMappingPolicy.MAPS_TO_HOLD,
    )
    assert result == DecisionDirection.HOLD


def test_conditional_uses_case_specific_override_under_option_c():
    result = map_assertion_state_to_direction(
        AssertionState.CONDITIONAL, conditional_policy=ConditionalMappingPolicy.CASE_SPECIFIC,
        case_specific_override=DecisionDirection.NEGATIVE,
    )
    assert result == DecisionDirection.NEGATIVE


def test_conditional_case_specific_without_override_returns_none():
    result = map_assertion_state_to_direction(
        AssertionState.CONDITIONAL, conditional_policy=ConditionalMappingPolicy.CASE_SPECIFIC,
    )
    assert result is None


# ---------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------

def _case_with_single_claim(domain, assertion_state, taxon="Synthetica agreement"):
    unit = ValidationUnit(
        taxon=taxon, plant_part="leaf",
        population="Adults", jurisdiction="EU",
        indication="Sleep and relaxation", route_of_administration="Oral",
    )
    reference = ReferenceDescriptor(
        reference_id="ref_agreement_1", source_type="EMA_HMPC", version="v1-test",
        document_date=date(2020, 1, 1),
    )
    claim = ReferenceClaim(
        domain=domain, assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="sleep", assertion_state=assertion_state,
        source_reference_id=reference.reference_id, source_locator="test section 1",
        evidence_text=NormalizedEvidenceText(
            original_text="Test.", normalized_text="Test.",
            transformation_type=TransformationType.SUMMARIZED_BY_CURATOR,
            transformation_version="test-fixture-v1", source_locator="test section 1",
        ),
    )
    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[domain] = check_applicability(reference, unit, domain)

    case = GoldCase(
        case_id=f"test_case_{domain.value}_{assertion_state.value}".replace(" ", "_").replace("/", "_"),
        validation_unit=unit, references=[gref],
        curation_status=CurationStatus.REFERENCE_CURATED,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


# ---------------------------------------------------------------------
# assess_agreement_eligibility()
# ---------------------------------------------------------------------

def test_present_indication_evidence_with_expected_output_is_eligible():
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.PRESENT)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.ELIGIBLE
    assert result.mapped_direction == DecisionDirection.POSITIVE


def test_missing_expected_output_is_not_eligible():
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.PRESENT)
    # expected_output left at its default (expected_decision_direction=None)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.EXPECTED_OUTPUT_NOT_SPECIFIED
    assert result.mapped_direction == DecisionDirection.POSITIVE  # still reported, for visibility


def test_safety_domain_only_is_not_eligible():
    """Current protocol policy (design doc §3): SAFETY is not (yet)
    eligible for whole-case decision_direction_agreement, regardless
    of AssertionState or whether expected_output happens to be set."""
    case = _case_with_single_claim(ReferenceDomain.SAFETY, AssertionState.PRESENT)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.NO_ELIGIBLE_DOMAIN_OUTCOME


def test_no_resolved_outcomes_is_not_eligible():
    unit = ValidationUnit(taxon="Empty taxon")
    case = GoldCase(case_id="empty_case", validation_unit=unit)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.NO_ELIGIBLE_DOMAIN_OUTCOME


def test_not_stated_indication_evidence_is_not_eligible():
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.NOT_STATED)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.ASSERTION_STATE_UNMAPPED


def test_conditional_indication_evidence_is_not_eligible_under_default_policy():
    """This is exactly Case 003's real, frozen situation, reproduced
    generically: CONDITIONAL + INDICATION_EVIDENCE + expected_output
    set is still NOT_ELIGIBLE under the adopted (UNRESOLVED) policy."""
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.CONDITIONAL)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.ASSERTION_STATE_UNMAPPED


def test_conditional_becomes_eligible_if_a_policy_is_explicitly_passed():
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.CONDITIONAL)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.HOLD)
    result = assess_agreement_eligibility(case, conditional_policy=ConditionalMappingPolicy.MAPS_TO_HOLD)
    assert result.eligibility == AgreementEligibility.ELIGIBLE
    assert result.mapped_direction == DecisionDirection.HOLD


def test_present_maps_positive_but_expected_output_negative_is_mismatch():
    """Required test 1: PRESENT maps POSITIVE, but ExpectedOutput is
    NEGATIVE -> NOT_ELIGIBLE / EXPECTED_OUTPUT_MAPPING_MISMATCH. A
    manually supplied ExpectedOutput must never silently override, or
    be silently trusted over, the prospective mapping."""
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.PRESENT)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.NEGATIVE)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.EXPECTED_OUTPUT_MAPPING_MISMATCH
    assert result.mapped_direction == DecisionDirection.POSITIVE


def test_absent_maps_negative_but_expected_output_positive_is_mismatch():
    """Required test 2: ABSENT maps NEGATIVE, but ExpectedOutput is
    POSITIVE -> NOT_ELIGIBLE / EXPECTED_OUTPUT_MAPPING_MISMATCH."""
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.ABSENT)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.EXPECTED_OUTPUT_MAPPING_MISMATCH
    assert result.mapped_direction == DecisionDirection.NEGATIVE


def test_matching_expected_output_is_eligible_not_mismatch():
    """Sanity complement to the two mismatch tests: an exact match is
    still ELIGIBLE, not accidentally caught by the new check."""
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.PRESENT)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE)
    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.ELIGIBLE
    assert result.reason is None


# ---------------------------------------------------------------------
# derive_expected_output_from_resolved_outcomes()
# ---------------------------------------------------------------------

def test_derive_populates_direction_from_present():
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.PRESENT)
    derived = derive_expected_output_from_resolved_outcomes(case)
    assert derived.expected_decision_direction == DecisionDirection.POSITIVE
    # original untouched
    assert case.expected_output.expected_decision_direction is None


def test_derive_leaves_unchanged_when_not_derivable():
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.CONDITIONAL)
    derived = derive_expected_output_from_resolved_outcomes(case)
    assert derived is case.expected_output  # unchanged object, nothing invented
    assert derived.expected_decision_direction is None


def test_derive_leaves_unchanged_for_safety_only_case():
    case = _case_with_single_claim(ReferenceDomain.SAFETY, AssertionState.PRESENT)
    derived = derive_expected_output_from_resolved_outcomes(case)
    assert derived is case.expected_output
    assert derived.expected_decision_direction is None


def test_derive_does_not_overwrite_a_matching_existing_direction():
    """Required test 3: derive does not overwrite a matching existing
    direction — returns the SAME object (nothing to do), not a new,
    merely equal-valued one."""
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.PRESENT)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE)
    derived = derive_expected_output_from_resolved_outcomes(case)
    assert derived is case.expected_output
    assert derived.expected_decision_direction == DecisionDirection.POSITIVE


def test_derive_raises_on_conflicting_existing_direction():
    """Required test 4: derive rejects (raises) a conflicting existing
    direction — never silently overwrites it, never silently keeps it
    while pretending derivation succeeded."""
    case = _case_with_single_claim(ReferenceDomain.INDICATION_EVIDENCE, AssertionState.PRESENT)
    case.expected_output = ExpectedOutput(expected_decision_direction=DecisionDirection.NEGATIVE)
    try:
        derive_expected_output_from_resolved_outcomes(case)
        raise AssertionError("expected ExpectedOutputDirectionConflictError, none was raised")
    except ExpectedOutputDirectionConflictError:
        pass  # expected


if __name__ == "__main__":
    import sys
    import traceback

    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_") and callable(obj)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
