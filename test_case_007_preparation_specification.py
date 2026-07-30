"""
Tests for Case 007 (Valeriana officinalis / PREPARATION_SPEC).

Scope: the MINIMUM tests needed to verify —
1. The underlying ReferenceClaim states the exact preparation specifications
   from the EMA/HMPC source — DER 3-7.4:1, ethanol 40-70% (V/V).
2. PREPARATION_SPECIFICATION assertion reaches ResolutionStatus.SELECTED with
   assertion_state=PRESENT (no ambiguity, single EMA_HMPC reference).
3. PREPARATION_SPEC is correctly NOT_ELIGIBLE for whole-case decision_direction_
   agreement (per protocol §14.1; this is PREPARATION_SPEC's documented behavior,
   same as SAFETY and IDENTITY_QUALITY).
4. Engine evidence remains empty on THIS file's own build function (no whole-case
   expected direction was set either) — Leakage-Rule-9.1 file-separation.
5. validation_unit.indication is deliberately None — PREPARATION_SPEC claims are
   not indication-dependent.
6. Plant part is exactly *radix* (root) — no leaf/herb confusion.
"""

from agreement_eligibility import assess_agreement_eligibility, AgreementEligibility, AgreementIneligibilityReason
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType
from gold_case_execution import execute_gold_case_against_engine
from gold_case_reference_grounded_007_valeriana_officinalis_preparation_spec import (
    build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec,
)
from reference_precedence import ResolutionStatus


def test_claim_subject_exactly_matches_eumhpc_specification():
    """(1) The ReferenceClaim's subject contains the exact DER and solvent
    range from EMA/HMPC/150846/2015 for well-established use."""
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()

    claim = case.references[0].claims[0]
    assert claim.subject == "dry extract, DER 3-7.4:1, extraction solvent ethanol 40-70% (V/V)"
    assert "3-7.4:1" in claim.subject or "3.0-7.4" in claim.subject
    assert "40-70%" in claim.subject
    assert "ethanol" in claim.subject.lower()


def test_preparation_spec_resolved_to_selected():
    """(2) ReferenceClaim with assertion_type=PREPARATION_SPECIFICATION,
    assertion_state=PRESENT, and a single EMA_HMPC reference resolves to
    ResolutionStatus.SELECTED."""
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()

    claim = case.references[0].claims[0]
    assert claim.assertion_type == AssertionType.PREPARATION_SPECIFICATION
    assert claim.assertion_state == AssertionState.PRESENT

    prep_outcomes = [o for o in case.resolved_outcomes if o.domain == ReferenceDomain.PREPARATION_SPEC]
    assert len(prep_outcomes) == 1
    outcome = prep_outcomes[0]

    assert outcome.resolution_status == ResolutionStatus.SELECTED
    assert outcome.assertion_state == AssertionState.PRESENT
    assert outcome.selected_reference_id == "EMA_HMPC_150846_2015_valeriana_officinalis_radix"


def test_preparation_spec_not_eligible_for_whole_case_agreement():
    """(3) assess_agreement_eligibility() correctly returns NOT_ELIGIBLE for
    PREPARATION_SPEC, per protocol §14.1. This is the expected, documented
    behavior — PREPARATION_SPEC does not yet map to a whole-case decision
    direction."""
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()

    eligibility = assess_agreement_eligibility(case)
    assert eligibility.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert eligibility.reason == AgreementIneligibilityReason.NO_ELIGIBLE_DOMAIN_OUTCOME


def test_engine_evidence_remains_empty_no_expected_direction():
    """(4) No EngineEvidenceInput was constructed on THIS file's build
    function — by Leakage-Rule-9.1 file-separation. No whole-case
    expected_decision_direction was set."""
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()
    assert case.engine_evidence == []
    assert case.engine_evidence_origin is None
    assert case.expected_output.expected_decision_direction is None


def test_indication_unset_preparation_spec_independent():
    """(5) validation_unit.indication is None — PREPARATION_SPEC claims are
    not indication-dependent. The specification is identical regardless of
    which indication the preparation is used for."""
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()
    assert case.validation_unit.indication is None


def test_plant_part_locked_to_radix_root_only():
    """(6) Plant part is exactly 'radix' (root) — no leaf/herb/aerial-parts
    confusion. PREPARATION_SPEC must be unambiguous about which part of the
    plant is being specified."""
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()
    assert case.validation_unit.plant_part == "radix"


def test_preparation_spec_not_required_for_execution_without_indication():
    """Confirms that a PREPARATION_SPEC case with no indication can execute
    the engine without raising GoldCaseNotExecutableError — PREPARATION_SPEC
    is outside INDICATION_REQUIRED_DOMAINS. Execution with no engine evidence
    is legitimate; the case tests whether the engine detects/represents the
    specified preparation."""
    case = build_gold_case_refgrounded_007_valeriana_officinalis_preparation_spec()
    assert case.validation_unit.indication is None
    # Should not raise for missing indication.
    result_df = execute_gold_case_against_engine(case)
    assert result_df is not None


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        test_claim_subject_exactly_matches_eumhpc_specification,
        test_preparation_spec_resolved_to_selected,
        test_preparation_spec_not_eligible_for_whole_case_agreement,
        test_engine_evidence_remains_empty_no_expected_direction,
        test_indication_unset_preparation_spec_independent,
        test_plant_part_locked_to_radix_root_only,
        test_preparation_spec_not_required_for_execution_without_indication,
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
    sys.exit(1 if failures else 0)
