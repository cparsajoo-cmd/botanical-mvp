"""Focused tests for Case 015 — Hypericum perforatum PREPARATION_SPEC."""

from agreement_eligibility import (
    AgreementEligibility,
    AgreementIneligibilityReason,
    assess_agreement_eligibility,
)
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType
from gold_case_reference_grounded_015_hypericum_perforatum_preparation_spec import (
    PREPARATION_TEXT,
    REFERENCE_ID,
    build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec,
)
from reference_precedence import ResolutionStatus


def test_exact_ema_preparation_text():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    claim = case.references[0].claims[0]
    assert claim.subject == PREPARATION_TEXT
    assert claim.evidence_text.original_text == PREPARATION_TEXT
    assert claim.evidence_text.transformation_type == "VERBATIM"


def test_preparation_fields_are_exact():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    prep = case.validation_unit.preparation
    assert prep.dosage_form == "Dry extract"
    assert prep.der_min == 3.0
    assert prep.der_max == 7.0
    assert prep.solvent == "methanol 80% (V/V)"


def test_taxon_and_plant_part_are_locked():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    assert case.validation_unit.taxon == "Hypericum perforatum L."
    assert case.validation_unit.plant_part == "herba"
    assert case.references[0].reference.taxon == "Hypericum perforatum L."
    assert case.references[0].reference.plant_part == "herba"


def test_preparation_claim_resolves_selected_present():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    claim = case.references[0].claims[0]
    assert claim.domain == ReferenceDomain.PREPARATION_SPEC
    assert claim.assertion_type == AssertionType.PREPARATION_SPECIFICATION
    assert claim.assertion_state == AssertionState.PRESENT
    outcomes = [o for o in case.resolved_outcomes if o.domain == ReferenceDomain.PREPARATION_SPEC]
    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.resolution_status == ResolutionStatus.SELECTED
    assert outcome.assertion_state == AssertionState.PRESENT
    assert outcome.selected_reference_id == REFERENCE_ID


def test_reference_is_current_final_ema_source():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    descriptor = case.references[0].reference
    assert descriptor.source_type == "EMA_HMPC"
    assert descriptor.version == "Revision 1, final"
    assert descriptor.retracted_or_superseded is False
    assert descriptor.document_date.isoformat() == "2023-02-22"


def test_applicability_is_computed_and_passes():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    result = case.references[0].applicability_by_domain[ReferenceDomain.PREPARATION_SPEC]
    assert result.applicable is True
    assert result.failed_dimensions == []


def test_no_engine_evidence_or_expected_direction_leakage():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    assert case.engine_evidence == []
    assert case.engine_evidence_origin is None
    assert case.expected_output.expected_decision_direction is None


def test_preparation_spec_not_eligible_for_whole_case_agreement():
    case = build_gold_case_refgrounded_015_hypericum_perforatum_preparation_spec()
    eligibility = assess_agreement_eligibility(case)
    assert eligibility.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert eligibility.reason == AgreementIneligibilityReason.NO_ELIGIBLE_DOMAIN_OUTCOME


if __name__ == "__main__":
    import traceback

    tests = [
        test_exact_ema_preparation_text,
        test_preparation_fields_are_exact,
        test_taxon_and_plant_part_are_locked,
        test_preparation_claim_resolves_selected_present,
        test_reference_is_current_final_ema_source,
        test_applicability_is_computed_and_passes,
        test_no_engine_evidence_or_expected_direction_leakage,
        test_preparation_spec_not_eligible_for_whole_case_agreement,
    ]
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
    raise SystemExit(1 if failures else 0)
