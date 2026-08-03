"""
Tests for Case 006 (Hypericum perforatum / SAFETY contraindication).

CORRECTED (this revision): the previous version of this file asserted
severity=None / resolution_status=INSUFFICIENT_METADATA / execution
raising GoldCaseNotExecutableError for missing indication — all
accurate for an EARLIER revision of Case 006's own file, but stale
once that file was updated to assign severity via
severity_assignment_policy.py and once gold_case_execution.py's
domain-aware indication architecture landed. This revision re-reads
the CURRENT Case 006 file and gold_case_execution.py and asserts what
they actually do now.

Scope, per explicit instruction: the MINIMUM tests needed to verify —
1. The underlying ReferenceClaim states assertion_state=PRESENT and
   its subject preserves ALL FOUR source-stated CYP pathways (CYP3A4,
   CYP2B6, CYP2C9, CYP2C19) plus P-glycoprotein — not narrowed to
   CYP3A4/P-gp alone.
2. severity_assignment_policy.py assigns SeverityLevel.SERIOUS to this
   claim (a documented repository rule, not curator judgment), and, as
   a direct, mechanical consequence, the case's SAFETY resolved
   outcome reaches ResolutionStatus.SELECTED with assertion_state=
   PRESENT, severity=SERIOUS, and selected_reference_id pointing at
   the governing EMA reference.
3. SAFETY is correctly NOT_ELIGIBLE for whole-case
   decision_direction_agreement (reason=NO_ELIGIBLE_DOMAIN_OUTCOME) —
   Protocol §14.1 behaves as documented, not worked around, and this
   holds regardless of (2).
4. Engine evidence remains empty on THIS file's own build function (no
   whole-case expected direction was set either) — Case 006's Ground
   Truth builder deliberately never attaches EngineEvidenceInput or
   runs the engine itself; that happens in the separate
   case_006_engine_evidence_run.py, per the Leakage-Rule-9.1
   file-separation convention Case 003 already established.
5. The WEU preparation is locked (exact preparation/population/route/
   claim_type/applicability metadata verified, not just an inequality
   check against "traditional-use"), and the governing claim text
   itself contains no Traditional-Use hyperforin dose-gating language.
6. validation_unit.indication is deliberately None, but Case 006 is
   NOT rejected merely because indication is absent — SAFETY is
   outside gold_case_execution.INDICATION_REQUIRED_DOMAINS, so
   execute_gold_case_against_engine() runs it. Execution still fails
   closed for genuinely missing MANDATORY non-indication metadata
   (dosage_form), and the separate engine-evidence execution path
   (case_006_engine_evidence_run.py) is confirmed to actually reach
   ExecutionReadiness.READY and execute the real engine.

Does not modify gold_case_reference_grounded_006_hypericum_perforatum_
safety_interaction.py, severity_assignment_policy.py, or engine
evidence wording. Does execute the real engine (via the separate
case_006_engine_evidence_run.py module) for test 6's third assertion,
same as case_006_engine_evidence_run.py's own __main__ already does.
"""

from dataclasses import replace

from agreement_eligibility import (
    AgreementEligibility, AgreementIneligibilityReason, assess_agreement_eligibility,
)
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, SeverityLevel
from execution_readiness import ExecutionReadiness
from gold_case_execution import GoldCaseNotExecutableError, execute_gold_case_against_engine
from gold_case_reference_grounded_006_hypericum_perforatum_safety_interaction import (
    build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction,
)
from reference_precedence import ResolutionStatus


def test_claim_subject_preserves_all_four_source_pathways():
    """(1) The underlying ReferenceClaim's subject preserves every
    pathway Section 4.3 actually names — CYP3A4, CYP2B6, CYP2C9,
    CYP2C19, and P-glycoprotein — not narrowed to CYP3A4/P-gp alone
    (the defect corrected in this revision). Checked on the claim
    itself, since the resolved outcome's subject is a normalized
    lowercase form of the same string."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()

    assert len(case.references) == 1
    claim = case.references[0].claims[0]
    subject_lower = claim.subject.lower()
    for pathway in ("cyp3a4", "cyp2b6", "cyp2c9", "cyp2c19", "p-glycoprotein"):
        assert pathway in subject_lower, f"{pathway!r} missing from claim.subject: {claim.subject!r}"

    assert claim.domain == ReferenceDomain.SAFETY
    assert claim.assertion_type == AssertionType.CONTRAINDICATION
    assert claim.assertion_state == AssertionState.PRESENT


def test_severity_assigned_via_policy_resolution_selected():
    """(2) claim.severity == SeverityLevel.SERIOUS, assigned by
    severity_assignment_policy.assign_contraindication_severity() — a
    documented repository rule, not curator judgment inside this
    file's docstring. As a direct, mechanical consequence, the SAFETY
    resolved outcome reaches ResolutionStatus.SELECTED, with
    assertion_state=PRESENT, severity=SERIOUS, and
    selected_reference_id pointing at the governing EMA reference."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()

    claim = case.references[0].claims[0]
    assert claim.severity == SeverityLevel.SERIOUS

    safety_outcomes = [o for o in case.resolved_outcomes if o.domain == ReferenceDomain.SAFETY]
    assert len(safety_outcomes) == 1
    outcome = safety_outcomes[0]

    assert outcome.assertion_type == AssertionType.CONTRAINDICATION
    assert outcome.resolution_status == ResolutionStatus.SELECTED
    assert outcome.assertion_state == AssertionState.PRESENT
    assert outcome.severity == SeverityLevel.SERIOUS
    assert outcome.selected_reference_id == "EMA_HMPC_7695_2021_hypericum_perforatum_herba"


def test_safety_domain_not_eligible_for_whole_case_agreement():
    """(3) assess_agreement_eligibility() — the real protocol mapping —
    returns NOT_ELIGIBLE with reason NO_ELIGIBLE_DOMAIN_OUTCOME, because
    ReferenceDomain.SAFETY is not in agreement_eligibility._ELIGIBLE_
    DOMAINS (Protocol §14.1: only INDICATION_EVIDENCE is presently
    eligible). This is correct, protocol-conforming behavior, not a
    defect this case tries to route around."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()

    result = assess_agreement_eligibility(case)
    assert result.eligibility == AgreementEligibility.NOT_ELIGIBLE
    assert result.reason == AgreementIneligibilityReason.NO_ELIGIBLE_DOMAIN_OUTCOME
    assert result.mapped_direction is None


def test_engine_evidence_remains_empty_and_no_whole_case_direction():
    """(4) No EngineEvidenceInput was constructed on THIS file's build
    function — by the Leakage-Rule-9.1 file-separation convention
    (execution happens in case_006_engine_evidence_run.py instead),
    not because execution is architecturally blocked. No whole-case
    expected_decision_direction was set either."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()
    assert case.engine_evidence == []
    assert case.engine_evidence_origin is None
    assert case.expected_output.expected_decision_direction is None


def test_weu_preparation_locked_no_traditional_use_reference():
    """(5) The locked preparation is exactly WEU preparation a) (DER
    3-7:1, methanol 80% V/V), identical on both the ReferenceDescriptor
    and the ValidationUnit; population/route/jurisdiction match the
    WEU posology; claim_type is 'well-established-use'; the reference
    is applicable for SAFETY against this exact ValidationUnit; and the
    claim's own verbatim text contains the unconditional WEU
    interaction-contraindication language WITHOUT the Traditional Use
    pathway's hyperforin dose-gating language (">1 mg" / "<= 1 mg" /
    "hyperforin") — i.e. this is substantively the WEU claim, not just
    a claim_type label that happens to say so."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()

    unit = case.validation_unit
    unit_prep = unit.preparation
    assert unit_prep.dosage_form == "Extract"
    assert unit_prep.solvent == "methanol 80% V/V"
    assert unit_prep.der_min == 3.0
    assert unit_prep.der_max == 7.0
    assert unit.population == "Adults and elderly"
    assert unit.route_of_administration == "Oral"
    assert unit.jurisdiction == "EU"

    assert len(case.references) == 1
    gref = case.references[0]
    ref = gref.reference
    ref_prep = ref.preparation
    assert (ref_prep.dosage_form, ref_prep.solvent, ref_prep.der_min, ref_prep.der_max) == (
        unit_prep.dosage_form, unit_prep.solvent, unit_prep.der_min, unit_prep.der_max
    )
    assert ref.population == unit.population
    assert ref.route_scope == ["Oral"]
    assert ref.jurisdiction == unit.jurisdiction
    assert ref.claim_type == "well-established-use"
    assert ref.claim_type != "traditional-use"

    applicability = gref.applicability_by_domain.get(ReferenceDomain.SAFETY)
    assert applicability is not None
    assert applicability.applicable is True
    assert applicability.failed_dimensions == []

    claim_text_lower = gref.claims[0].evidence_text.original_text.lower()
    assert "concomitant use with coumarin-type anticoagulants" in claim_text_lower
    assert "hyperforin" not in claim_text_lower
    assert "> 1 mg" not in claim_text_lower
    assert "1 mg/day" not in claim_text_lower


def test_indication_absent_does_not_block_execution_but_dosage_form_still_does():
    """(6) validation_unit.indication is deliberately None, and Case
    006 is NOT rejected merely because indication is absent — SAFETY
    is outside gold_case_execution.INDICATION_REQUIRED_DOMAINS, so
    execute_gold_case_against_engine() runs the case with no evidence
    at all (a legitimate, meaningful case per that function's own
    docstring: no evidence -> NOT_EVALUABLE-leaning gates, not an
    error). Execution still fails closed for genuinely missing
    MANDATORY non-indication metadata (dosage_form), proving this
    isn't a blanket 'skip all validation' change — only indication
    was widened. Finally, confirms the separate engine-evidence
    execution path (case_006_engine_evidence_run.py) actually reaches
    ExecutionReadiness.READY and executes the real engine, rather than
    this file's own build function ever doing so."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()
    assert case.validation_unit.indication is None

    # Not rejected merely for missing indication — runs with no
    # evidence, returns a real (possibly empty-signal) result_df,
    # never raises GoldCaseNotExecutableError.
    result_df = execute_gold_case_against_engine(case)
    assert result_df is not None

    # Execution still fails closed for missing MANDATORY non-indication
    # metadata (dosage_form) — the widening is domain-scoped to
    # indication only, not a general relaxation of GoldCaseNotExecutableError.
    unit_without_preparation = replace(case.validation_unit, preparation=None)
    case_without_preparation = replace(case, validation_unit=unit_without_preparation)
    try:
        execute_gold_case_against_engine(case_without_preparation)
        assert False, "expected GoldCaseNotExecutableError for missing dosage_form"
    except GoldCaseNotExecutableError as exc:
        assert "dosage_form" in str(exc)

    # The separate engine-evidence execution path is what's actually
    # used for real execution — confirmed to reach READY and execute.
    from case_006_engine_evidence_run import run_case_006_through_readiness_gate
    _case_with_evidence, readiness, evidence_result_df = run_case_006_through_readiness_gate()
    assert readiness.decision == ExecutionReadiness.READY
    assert evidence_result_df is not None
    assert not evidence_result_df.empty


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        test_claim_subject_preserves_all_four_source_pathways,
        test_severity_assigned_via_policy_resolution_selected,
        test_safety_domain_not_eligible_for_whole_case_agreement,
        test_engine_evidence_remains_empty_and_no_whole_case_direction,
        test_weu_preparation_locked_no_traditional_use_reference,
        test_indication_absent_does_not_block_execution_but_dosage_form_still_does,
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
