"""
Tests for the evidence-channel-unification invariant in
gold_case_execution.execute_gold_case_with_readiness_gate().

WHAT THIS COVERS
The six required scenarios: GoldCase.engine_evidence and the explicit
evidence= parameter must resolve to ONE effective_evidence value that
both execution_readiness.assess_execution_readiness() and
execute_gold_case_against_engine() receive identically. Never a
silent preference between the two channels when both are populated
and differ — that case must fail closed
(EvidenceChannelConflictError).

These use minimal, deterministic, SYNTHETIC GoldCases (not Case 003 —
kept independent of any one real case so this invariant is verified
generically). No network, no Supabase, botanical_rd_candidate_engine.py
never modified.
"""

from datetime import date

import pandas as pd

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus,
    ExtractionConfidenceLevel, GoldCaseKind, TransformationType,
)
from engine_evidence_input import EngineEvidenceInput
from execution_readiness import (
    DimensionAssessment, EquivalenceJustification, ExecutionReadiness,
    ScopeDimension, ScopeEquivalence,
)
from gold_case import GoldCase, GoldCaseReference
from gold_case_execution import (
    EvidenceChannelConflictError,
    _resolve_effective_evidence,
    execute_gold_case_with_readiness_gate,
)
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit


def _minimal_ready_case(taxon="Synthetica evidencia") -> GoldCase:
    unit = ValidationUnit(
        taxon=taxon, plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="Adults", jurisdiction="EU",
        indication="Sleep and relaxation", route_of_administration="Oral",
    )
    reference = ReferenceDescriptor(
        reference_id="synthetic_ref_evidence_channel", source_type="EMA_HMPC",
        version="v1-synthetic", document_date=date(2020, 1, 1),
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="general",
    )
    claim = ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE, assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="sleep", assertion_state=AssertionState.PRESENT,
        source_reference_id=reference.reference_id, source_locator="synthetic section 1",
        evidence_text=NormalizedEvidenceText(
            original_text="Synthetic.", normalized_text="Synthetic.",
            transformation_type=TransformationType.SUMMARIZED_BY_CURATOR,
            transformation_version="test-fixture-v1", source_locator="synthetic section 1",
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH, basis="test fixture",
            extractor_type="human_curator", extractor_version="test-fixture-v1",
        ),
    )
    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        reference, unit, ReferenceDomain.INDICATION_EVIDENCE,
    )
    case = GoldCase(
        case_id=f"synthetic_evidence_channel_{taxon}", validation_unit=unit, references=[gref],
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def _evidence(taxon="Synthetica evidencia", note="Synthetic independent evidence text."):
    return [EngineEvidenceInput(scientific_name=taxon, target_indication="Sleep quality", notes=note)]


def _exact_dims():
    return (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.POPULATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
    )


_EMPTY_DFS = dict(compound_profiles_df=pd.DataFrame(), scientific_evidence_df=pd.DataFrame(), use_live_search=False)


# 1. Case field populated, no explicit parameter -> Guard and Engine receive the case evidence.
def test_case_field_only_reaches_both_guard_and_engine():
    case = _minimal_ready_case()
    from dataclasses import replace
    case = replace(case, engine_evidence=_evidence())

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case, dimension_assessments=_exact_dims(), evidence=None, **_EMPTY_DFS,
    )

    assert readiness.decision == ExecutionReadiness.READY, readiness.reasons
    assert result_df is not None
    gate = result_df.iloc[0]["Gate_Results"]["minimum_evidence"]
    assert gate["status"].value == "passed"


# 2. Explicit parameter populated, case field empty -> Guard and Engine receive the explicit evidence.
def test_explicit_parameter_only_reaches_both_guard_and_engine():
    case = _minimal_ready_case()  # engine_evidence defaults to []
    evidence = _evidence()

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case, dimension_assessments=_exact_dims(), evidence=evidence, **_EMPTY_DFS,
    )

    assert readiness.decision == ExecutionReadiness.READY, readiness.reasons
    assert result_df is not None
    gate = result_df.iloc[0]["Gate_Results"]["minimum_evidence"]
    assert gate["status"].value == "passed"


# 3. Both populated identically -> one successful, consistent path.
def test_both_channels_identical_succeeds():
    from dataclasses import replace
    evidence = _evidence()
    case = replace(_minimal_ready_case(), engine_evidence=evidence)

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case, dimension_assessments=_exact_dims(), evidence=evidence, **_EMPTY_DFS,
    )

    assert readiness.decision == ExecutionReadiness.READY, readiness.reasons
    assert result_df is not None
    gate = result_df.iloc[0]["Gate_Results"]["minimum_evidence"]
    assert gate["status"].value == "passed"


# 4. Both populated but differ -> deterministic fail-closed behavior.
def test_both_channels_populated_and_different_fails_closed():
    from dataclasses import replace
    case_evidence = _evidence(note="Case-field evidence text.")
    explicit_evidence = _evidence(note="A completely different evidence text.")
    case = replace(_minimal_ready_case(), engine_evidence=case_evidence)

    try:
        execute_gold_case_with_readiness_gate(
            case, dimension_assessments=_exact_dims(), evidence=explicit_evidence, **_EMPTY_DFS,
        )
        raise AssertionError("expected EvidenceChannelConflictError, none was raised")
    except EvidenceChannelConflictError:
        pass  # expected — fail-closed confirmed


# 5. Neither populated -> DEFER / NO_ENGINE_EVIDENCE.
def test_neither_channel_populated_defers():
    case = _minimal_ready_case()

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case, dimension_assessments=_exact_dims(), evidence=None, **_EMPTY_DFS,
    )

    from execution_readiness import ReadinessReasonCode
    assert readiness.decision == ExecutionReadiness.DEFER
    assert ReadinessReasonCode.NO_ENGINE_EVIDENCE in readiness.reasons
    assert result_df is None


# 6. Evidence notes properly wired -> minimum_evidence receives and recognizes the clinical evidence.
def test_notes_content_is_recognized_as_clinical_evidence_by_the_gate():
    from dataclasses import replace
    evidence = [EngineEvidenceInput(
        scientific_name="Synthetica evidencia", target_indication="Sleep quality",
        notes=(
            "A randomized controlled trial found significantly improved "
            "sleep quality scores compared with placebo."
        ),
    )]
    case = replace(_minimal_ready_case(), engine_evidence=evidence)

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case, dimension_assessments=_exact_dims(), evidence=None, **_EMPTY_DFS,
    )

    assert readiness.decision == ExecutionReadiness.READY, readiness.reasons
    gate = result_df.iloc[0]["Gate_Results"]["minimum_evidence"]
    assert gate["status"].value == "passed"
    assert gate["evidence"] == "Clinical / human evidence"


# Unit-level tests of _resolve_effective_evidence() itself, isolated from the wrapper.
def test_resolve_effective_evidence_none_uses_case_field():
    from dataclasses import replace
    case_evidence = _evidence()
    case = replace(_minimal_ready_case(), engine_evidence=case_evidence)
    assert _resolve_effective_evidence(case, None) == case_evidence


def test_resolve_effective_evidence_empty_explicit_list_uses_case_field():
    from dataclasses import replace
    case_evidence = _evidence()
    case = replace(_minimal_ready_case(), engine_evidence=case_evidence)
    assert _resolve_effective_evidence(case, []) == case_evidence


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
