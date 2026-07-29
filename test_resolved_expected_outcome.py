"""Tests for resolved_expected_outcome.py (v4 correction #5: grouping
by assertion identity, not just domain)."""

from applicability_check import ReferenceDomain, ApplicabilityResult
from assertion_vocabulary import AssertionState, AssertionType, SeverityLevel
from reference_claim import ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from reference_precedence import ResolutionStatus
from resolved_expected_outcome import (
    group_claims_by_assertion_identity, resolve_expected_outcomes,
    derive_reference_verdict_from_claim,
)


class _FakeGoldCaseReference:
    def __init__(self, reference, claims, applicability_by_domain=None):
        self.reference = reference
        self.claims = claims
        self.applicability_by_domain = applicability_by_domain or {}


class _FakeGoldCase:
    def __init__(self, references):
        self.references = references


def _applicable(ref_id, domain):
    return ApplicabilityResult(reference_id=ref_id, domain=domain, applicable=True)


def _inapplicable(ref_id, domain):
    return ApplicabilityResult(reference_id=ref_id, domain=domain, applicable=False, failed_dimensions=[])


# ---------------------------------------------------------------------
# derive_reference_verdict_from_claim
# ---------------------------------------------------------------------

def test_derive_verdict_carries_severity_and_reference_id():
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.PRESENT,
        severity=SeverityLevel.SERIOUS, source_reference_id="ref1",
    )
    verdict = derive_reference_verdict_from_claim(claim)
    assert verdict.reference_id == "ref1"
    assert verdict.safety_severity == "SERIOUS"
    assert "Contraindication" in verdict.verdict_value


def test_derive_verdict_none_severity_stays_none():
    claim = ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE, assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="sleep", assertion_state=AssertionState.PRESENT, source_reference_id="ref1",
    )
    verdict = derive_reference_verdict_from_claim(claim)
    assert verdict.safety_severity is None


# ---------------------------------------------------------------------
# group_claims_by_assertion_identity — v4 correction #5
# ---------------------------------------------------------------------

def test_pregnancy_variant_claims_group_together():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    ref2 = ReferenceDescriptor(reference_id="r2", source_type="WHO_MONOGRAPH", version="v1")
    claim1 = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnant women", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    claim2 = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="use in pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r2")
    gref1 = _FakeGoldCaseReference(ref1, [claim1])
    gref2 = _FakeGoldCaseReference(ref2, [claim2])
    groups = group_claims_by_assertion_identity([gref1, gref2])
    assert len(groups) == 1


def test_different_subjects_never_grouped_together():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    claim_pregnancy = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    claim_hepatic = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="hepatic impairment", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    gref = _FakeGoldCaseReference(ref1, [claim_pregnancy, claim_hepatic])
    groups = group_claims_by_assertion_identity([gref])
    assert len(groups) == 2


def test_different_assertion_types_not_grouped_even_if_same_subject():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    claim_contra = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    claim_interaction = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.INTERACTION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    gref = _FakeGoldCaseReference(ref1, [claim_contra, claim_interaction])
    groups = group_claims_by_assertion_identity([gref])
    assert len(groups) == 2


def test_different_domains_not_grouped_even_if_same_subject_and_type():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    claim_safety = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.RESTRICTION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    claim_regulatory = ReferenceClaim(domain=ReferenceDomain.REGULATORY_STATUS, assertion_type=AssertionType.RESTRICTION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    gref = _FakeGoldCaseReference(ref1, [claim_safety, claim_regulatory])
    groups = group_claims_by_assertion_identity([gref])
    assert len(groups) == 2


def test_empty_references_gives_empty_groups():
    assert group_claims_by_assertion_identity([]) == {}


# ---------------------------------------------------------------------
# resolve_expected_outcomes — full pipeline
# ---------------------------------------------------------------------

def test_no_applicable_claims_gives_no_applicable_reference():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    claim = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    gref = _FakeGoldCaseReference(ref1, [claim], {ReferenceDomain.SAFETY: _inapplicable("r1", ReferenceDomain.SAFETY)})
    gc = _FakeGoldCase([gref])
    outcomes = resolve_expected_outcomes(gc)
    assert len(outcomes) == 1
    assert outcomes[0].resolution_status == ResolutionStatus.NO_APPLICABLE_REFERENCE
    assert outcomes[0].assertion_state is None


def test_single_applicable_claim_resolves_to_selected():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    claim = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.SERIOUS, source_reference_id="r1")
    gref = _FakeGoldCaseReference(ref1, [claim], {ReferenceDomain.SAFETY: _applicable("r1", ReferenceDomain.SAFETY)})
    gc = _FakeGoldCase([gref])
    outcomes = resolve_expected_outcomes(gc)
    assert outcomes[0].resolution_status == ResolutionStatus.SELECTED
    assert outcomes[0].assertion_state == AssertionState.PRESENT
    assert outcomes[0].severity == SeverityLevel.SERIOUS
    assert outcomes[0].selected_reference_id == "r1"


def test_most_severe_applicable_claim_wins_safety_domain():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="ESCOP_MONOGRAPH", version="v1")
    ref2 = ReferenceDescriptor(reference_id="r2", source_type="EMA_HMPC", version="v1")
    claim1 = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.SERIOUS, source_reference_id="r1")
    claim2 = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.MINOR, source_reference_id="r2")
    gref1 = _FakeGoldCaseReference(ref1, [claim1], {ReferenceDomain.SAFETY: _applicable("r1", ReferenceDomain.SAFETY)})
    gref2 = _FakeGoldCaseReference(ref2, [claim2], {ReferenceDomain.SAFETY: _applicable("r2", ReferenceDomain.SAFETY)})
    gc = _FakeGoldCase([gref1, gref2])
    outcomes = resolve_expected_outcomes(gc)
    assert outcomes[0].selected_reference_id == "r1"  # SERIOUS beats MINOR despite lower rank
    assert outcomes[0].severity == SeverityLevel.SERIOUS


def test_conflicting_non_safety_claims_give_reference_conflict():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="WHO_MONOGRAPH", version="v1")
    ref2 = ReferenceDescriptor(reference_id="r2", source_type="WHO_MONOGRAPH", version="v1")
    claim1 = ReferenceClaim(domain=ReferenceDomain.INDICATION_EVIDENCE, assertion_type=AssertionType.SUPPORTS_INDICATION, subject="sleep", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    claim2 = ReferenceClaim(domain=ReferenceDomain.INDICATION_EVIDENCE, assertion_type=AssertionType.SUPPORTS_INDICATION, subject="sleep", assertion_state=AssertionState.ABSENT, source_reference_id="r2")
    gref1 = _FakeGoldCaseReference(ref1, [claim1], {ReferenceDomain.INDICATION_EVIDENCE: _applicable("r1", ReferenceDomain.INDICATION_EVIDENCE)})
    gref2 = _FakeGoldCaseReference(ref2, [claim2], {ReferenceDomain.INDICATION_EVIDENCE: _applicable("r2", ReferenceDomain.INDICATION_EVIDENCE)})
    gc = _FakeGoldCase([gref1, gref2])
    outcomes = resolve_expected_outcomes(gc)
    assert outcomes[0].resolution_status == ResolutionStatus.REFERENCE_CONFLICT
    assert outcomes[0].assertion_state is None


def test_inapplicable_claim_excluded_from_precedence_even_if_more_severe():
    # Direct regression for the precautionary-safety-after-applicability
    # requirement.
    ref_inapplicable = ReferenceDescriptor(reference_id="r_bad", source_type="EMA_HMPC", version="v1")
    ref_applicable = ReferenceDescriptor(reference_id="r_good", source_type="ESCOP_MONOGRAPH", version="v1")
    claim_bad = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.SERIOUS, source_reference_id="r_bad")
    claim_good = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.MINOR, source_reference_id="r_good")
    gref_bad = _FakeGoldCaseReference(ref_inapplicable, [claim_bad], {ReferenceDomain.SAFETY: _inapplicable("r_bad", ReferenceDomain.SAFETY)})
    gref_good = _FakeGoldCaseReference(ref_applicable, [claim_good], {ReferenceDomain.SAFETY: _applicable("r_good", ReferenceDomain.SAFETY)})
    gc = _FakeGoldCase([gref_bad, gref_good])
    outcomes = resolve_expected_outcomes(gc)
    assert outcomes[0].selected_reference_id == "r_good"
    assert outcomes[0].severity == SeverityLevel.MINOR


def test_resolved_outcome_carries_all_required_version_fields():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    claim = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    gref = _FakeGoldCaseReference(ref1, [claim], {ReferenceDomain.SAFETY: _applicable("r1", ReferenceDomain.SAFETY)})
    gc = _FakeGoldCase([gref])
    outcomes = resolve_expected_outcomes(gc)
    outcome = outcomes[0]
    assert outcome.translation_rule_id
    assert outcome.translation_rule_version
    assert outcome.precedence_policy_version
    assert outcome.applicability_policy_version
    assert outcome.subject_normalization_rule_version


def test_resolve_expected_outcomes_never_mutates_input():
    ref1 = ReferenceDescriptor(reference_id="r1", source_type="EMA_HMPC", version="v1")
    claim = ReferenceClaim(domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION, subject="pregnancy", assertion_state=AssertionState.PRESENT, source_reference_id="r1")
    gref = _FakeGoldCaseReference(ref1, [claim], {ReferenceDomain.SAFETY: _applicable("r1", ReferenceDomain.SAFETY)})
    gc = _FakeGoldCase([gref])
    resolve_expected_outcomes(gc)
    assert gref.claims == [claim]  # unchanged
    assert len(gref.applicability_by_domain) == 1  # unchanged


def test_empty_gold_case_gives_empty_outcomes():
    gc = _FakeGoldCase([])
    assert resolve_expected_outcomes(gc) == []
