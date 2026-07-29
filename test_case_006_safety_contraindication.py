"""
Tests for Case 006 (Hypericum perforatum / SAFETY contraindication).

Scope, per explicit instruction: the MINIMUM tests needed to verify —
1. The underlying ReferenceClaim states assertion_state=PRESENT and
   its subject preserves ALL FOUR source-stated CYP pathways (CYP3A4,
   CYP2B6, CYP2C9, CYP2C19) plus P-glycoprotein — not narrowed to
   CYP3A4/P-gp alone. Severity is deliberately left unresolved (None),
   and — as a direct, mechanical consequence of that, not a separately
   invented status — the case's SAFETY resolved outcome is
   resolution_status=INSUFFICIENT_METADATA, not SELECTED.
2. SAFETY is correctly NOT_ELIGIBLE for whole-case
   decision_direction_agreement (reason=NO_ELIGIBLE_DOMAIN_OUTCOME) —
   Protocol §14.1 behaves as documented, not worked around, and this
   holds regardless of the severity/resolution-status change in (1).
3. Engine evidence remains empty and no whole-case expected direction
   was set.
4. The WEU preparation is locked (exact preparation/population/route/
   claim_type/applicability metadata verified, not just an inequality
   check against "traditional-use"), and the governing claim text
   itself contains no Traditional-Use hyperforin dose-gating language.
5. validation_unit.indication is deliberately left unset, and
   attempting to execute this case against the engine fails closed
   with GoldCaseNotExecutableError — the open architectural question
   is a real, enforced stop condition, not just a comment.

Does not execute the real engine's evaluation path, does not modify
gold_case_reference_grounded_006_hypericum_perforatum_safety_
interaction.py or any other existing file.
"""

from agreement_eligibility import (
    AgreementEligibility, AgreementIneligibilityReason, assess_agreement_eligibility,
)
from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType
from gold_case_execution import GoldCaseNotExecutableError, execute_gold_case_against_engine
from gold_case_reference_grounded_006_hypericum_perforatum_safety_interaction import (
    build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction,
)
from reference_precedence import ResolutionStatus


def test_claim_subject_preserves_all_four_source_pathways():
    """(1a) The underlying ReferenceClaim's subject preserves every
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


def test_severity_left_unresolved_no_explicit_rule_exists():
    """(1b) claim.severity is None — not SERIOUS, not any other
    SeverityLevel — because no explicit repository rule maps this
    contraindication class to a severity (confirmed by inspecting
    VALIDATION_PROTOCOL.md, assertion_vocabulary.py, and
    reference_precedence.py; none defines such a rule). As a direct,
    mechanical consequence (not a separately invented status), the
    SAFETY resolved outcome's resolution_status is
    INSUFFICIENT_METADATA, not SELECTED, and its assertion_state/
    severity are both None."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()

    claim = case.references[0].claims[0]
    assert claim.severity is None

    safety_outcomes = [o for o in case.resolved_outcomes if o.domain == ReferenceDomain.SAFETY]
    assert len(safety_outcomes) == 1
    outcome = safety_outcomes[0]

    assert outcome.assertion_type == AssertionType.CONTRAINDICATION
    assert outcome.resolution_status == ResolutionStatus.INSUFFICIENT_METADATA
    assert outcome.assertion_state is None
    assert outcome.severity is None
    assert outcome.selected_reference_id is None


def test_safety_domain_not_eligible_for_whole_case_agreement():
    """(2) assess_agreement_eligibility() — the real protocol mapping —
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
    """(3) No EngineEvidenceInput was constructed for this case, and no
    whole-case expected_decision_direction was set."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()
    assert case.engine_evidence == []
    assert case.engine_evidence_origin is None
    assert case.expected_output.expected_decision_direction is None


def test_weu_preparation_locked_no_traditional_use_reference():
    """(4) The locked preparation is exactly WEU preparation a) (DER
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


def test_indication_left_unset_and_execution_fails_closed():
    """(5) validation_unit.indication is deliberately None (the open
    architectural question documented in the case file's module
    docstring is not silently worked around), and actually attempting
    to execute this case against the engine fails closed with
    GoldCaseNotExecutableError rather than running with a guessed
    indication value."""
    case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()
    assert case.validation_unit.indication is None

    try:
        execute_gold_case_against_engine(case)
        assert False, "expected GoldCaseNotExecutableError, engine ran instead"
    except GoldCaseNotExecutableError as exc:
        assert "indication" in str(exc)


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        test_claim_subject_preserves_all_four_source_pathways,
        test_severity_left_unresolved_no_explicit_rule_exists,
        test_safety_domain_not_eligible_for_whole_case_agreement,
        test_engine_evidence_remains_empty_and_no_whole_case_direction,
        test_weu_preparation_locked_no_traditional_use_reference,
        test_indication_left_unset_and_execution_fails_closed,
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
