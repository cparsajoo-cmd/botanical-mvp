"""
Tests for gold_case_execution.py's domain-aware indication architecture
(INDICATION_REQUIRED_DOMAINS / _case_claim_domains() / _requires_
indication()) — independent of Case 006, and independent of Cases
001-005's own files (uses minimal synthetic fixtures built directly,
mirroring test_gold_case_execution.py's own _executable_case()
convention).
"""

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType
from engine_evidence_input import EngineEvidenceInput
from gold_case import GoldCase, GoldCaseReference
from gold_case_execution import (
    INDICATION_REQUIRED_DOMAINS,
    GoldCaseNotExecutableError,
    _case_claim_domains,
    _requires_indication,
    execute_gold_case_against_engine,
)
from reference_claim import ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from validation_unit import PreparationSpec, ValidationUnit


def _minimal_claim(domain: ReferenceDomain, assertion_type=AssertionType.SUPPORTS_INDICATION) -> ReferenceClaim:
    return ReferenceClaim(
        domain=domain,
        assertion_type=assertion_type,
        subject="test subject",
        assertion_state=AssertionState.PRESENT,
        source_reference_id="TEST_REF",
        source_locator="test locator",
    )


def _case_with_domains(domains, taxon="TestTaxon", indication=None, preparation=None) -> GoldCase:
    """Builds a minimal GoldCase whose claims declare exactly the
    given domains (one GoldCaseReference per domain, for simplicity).
    No applicability/resolved_outcomes computed — irrelevant to the
    indication-requirement question this file tests."""
    unit = ValidationUnit(
        taxon=taxon,
        indication=indication,
        preparation=preparation if preparation is not None else PreparationSpec(dosage_form="Infusion"),
        jurisdiction="EU",
    )
    refs = []
    for domain in domains:
        reference = ReferenceDescriptor(reference_id=f"TEST_REF_{domain.name}", source_type="EMA_HMPC", version="v1")
        claim = _minimal_claim(domain)
        refs.append(GoldCaseReference(reference=reference, claims=[claim]))
    return GoldCase(case_id="test_case", validation_unit=unit, references=refs)


# ---------------------------------------------------------------------
# INDICATION_REQUIRED_DOMAINS / _case_claim_domains / _requires_indication
# ---------------------------------------------------------------------

def test_indication_required_domains_contains_only_indication_evidence():
    """The whitelist is exactly {INDICATION_EVIDENCE} today — a
    regression lock so a future, careless addition/removal is caught
    explicitly rather than silently changing behavior."""
    assert INDICATION_REQUIRED_DOMAINS == frozenset({ReferenceDomain.INDICATION_EVIDENCE})


def test_indication_evidence_domain_requires_indication():
    case = _case_with_domains([ReferenceDomain.INDICATION_EVIDENCE])
    assert _case_claim_domains(case) == {ReferenceDomain.INDICATION_EVIDENCE}
    assert _requires_indication(case) is True


def test_safety_only_domain_does_not_require_indication():
    case = _case_with_domains([ReferenceDomain.SAFETY])
    assert _case_claim_domains(case) == {ReferenceDomain.SAFETY}
    assert _requires_indication(case) is False


def test_empty_claim_domain_set_fails_safe_and_requires_indication():
    """A case with no references/claims at all -> empty domain set ->
    requires indication (fail-safe: this function only ever WIDENS
    what's optional for a domain explicitly reasoned about, never
    narrows the requirement by omission)."""
    case = GoldCase(case_id="test_case", validation_unit=ValidationUnit(taxon="TestTaxon"))
    assert _case_claim_domains(case) == set()
    assert _requires_indication(case) is True


def test_mixed_domain_case_fails_safe_and_requires_indication():
    """A case whose claims declare BOTH SAFETY and INDICATION_EVIDENCE
    still requires indication — any intersection with
    INDICATION_REQUIRED_DOMAINS forces the requirement, even though
    SAFETY alone would not."""
    case = _case_with_domains([ReferenceDomain.SAFETY, ReferenceDomain.INDICATION_EVIDENCE])
    assert _case_claim_domains(case) == {ReferenceDomain.SAFETY, ReferenceDomain.INDICATION_EVIDENCE}
    assert _requires_indication(case) is True


def test_other_non_indication_domains_also_do_not_require_indication():
    """IDENTITY_QUALITY, REGULATORY_STATUS, and PREPARATION_SPEC are
    equally outside the whitelist — SAFETY is not a special case among
    these, it's simply the one Case 006 actually exercises."""
    for domain in (
        ReferenceDomain.IDENTITY_QUALITY,
        ReferenceDomain.REGULATORY_STATUS,
        ReferenceDomain.PREPARATION_SPEC,
    ):
        case = _case_with_domains([domain])
        assert _requires_indication(case) is False, f"{domain!r} unexpectedly requires indication"


# ---------------------------------------------------------------------
# execute_gold_case_against_engine() integration with the above
# ---------------------------------------------------------------------

def test_indication_dependent_case_still_raises_when_indication_missing():
    """Cases 001-005's own behavior, reproduced with a minimal
    synthetic fixture rather than importing their frozen files:
    INDICATION_EVIDENCE domain + indication=None -> raises
    GoldCaseNotExecutableError mentioning indication."""
    case = _case_with_domains([ReferenceDomain.INDICATION_EVIDENCE], indication=None)
    try:
        execute_gold_case_against_engine(case)
        assert False, "expected GoldCaseNotExecutableError"
    except GoldCaseNotExecutableError as exc:
        assert "indication" in str(exc)


def test_indication_dependent_case_does_not_raise_when_indication_present():
    """Same domain, but indication IS set -> does not raise for
    indication (may still legitimately run with no evidence)."""
    case = _case_with_domains([ReferenceDomain.INDICATION_EVIDENCE], indication="TestIndication")
    result_df = execute_gold_case_against_engine(case)
    assert result_df is not None


def test_safety_only_case_does_not_raise_when_indication_missing():
    """The core architecture fix under test: SAFETY-only + indication=
    None does NOT raise GoldCaseNotExecutableError."""
    case = _case_with_domains([ReferenceDomain.SAFETY], indication=None)
    result_df = execute_gold_case_against_engine(case)
    assert result_df is not None


def test_safety_only_case_still_raises_for_missing_dosage_form():
    """The widening is scoped to indication only — a SAFETY-only case
    still fails closed for missing MANDATORY preparation/dosage_form
    metadata."""
    unit = ValidationUnit(taxon="TestTaxon", indication=None, preparation=None, jurisdiction="EU")
    reference = ReferenceDescriptor(reference_id="TEST_REF_SAFETY", source_type="EMA_HMPC", version="v1")
    claim = _minimal_claim(ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION)
    case = GoldCase(
        case_id="test_case", validation_unit=unit,
        references=[GoldCaseReference(reference=reference, claims=[claim])],
    )
    try:
        execute_gold_case_against_engine(case)
        assert False, "expected GoldCaseNotExecutableError"
    except GoldCaseNotExecutableError as exc:
        assert "dosage_form" in str(exc)


def test_engine_evidence_input_target_indication_none_is_valid():
    """EngineEvidenceInput(target_indication=None) constructs without
    error and round-trips as None — the required-field default change
    this architecture depends on."""
    evidence = EngineEvidenceInput(scientific_name="TestTaxon", target_indication=None, notes="test notes")
    assert evidence.target_indication is None


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        test_indication_required_domains_contains_only_indication_evidence,
        test_indication_evidence_domain_requires_indication,
        test_safety_only_domain_does_not_require_indication,
        test_empty_claim_domain_set_fails_safe_and_requires_indication,
        test_mixed_domain_case_fails_safe_and_requires_indication,
        test_other_non_indication_domains_also_do_not_require_indication,
        test_indication_dependent_case_still_raises_when_indication_missing,
        test_indication_dependent_case_does_not_raise_when_indication_present,
        test_safety_only_case_does_not_raise_when_indication_missing,
        test_safety_only_case_still_raises_for_missing_dosage_form,
        test_engine_evidence_input_target_indication_none_is_valid,
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
