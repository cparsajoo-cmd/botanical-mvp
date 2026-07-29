"""
Tests for execution_readiness.py (Phase 3B-C guard).

These GoldCases are minimal, SYNTHETIC, and built only to exercise the
readiness guard's own logic in isolation — they are not real curated
cases and must never be confused with Case 001 or any other
Reference-Grounded GoldCase.
"""

from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus,
    ExtractionConfidenceLevel, GoldCaseKind, TransformationType,
)
from engine_evidence_input import EngineEvidenceInput
from execution_readiness import (
    DimensionAssessment, EquivalenceJustification, ExecutionReadiness,
    ExecutionReadinessInput, ReadinessReasonCode, ScopeDimension,
    ScopeEquivalence, assess_execution_readiness,
)
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit


def _evidence_text(text, locator):
    return NormalizedEvidenceText(
        original_text=text, normalized_text=text,
        transformation_type=TransformationType.SUMMARIZED_BY_CURATOR,
        transformation_version="test-fixture-v1", source_locator=locator,
    )


def _confidence():
    return ExtractionConfidence(
        level=ExtractionConfidenceLevel.HIGH, basis="test fixture",
        extractor_type="human_curator", extractor_version="test-fixture-v1",
    )


def _build_case(taxon, engine_evidence=(), reference_id="ref_1"):
    """Minimal, lockable, SYNTHETIC GoldCase for testing the readiness
    guard in isolation. SYNTHETIC/SUMMARIZED_BY_CURATOR is used
    deliberately here (permitted only for SYNTHETIC cases) since these
    are pipeline-mechanics tests, not real curation."""
    unit = ValidationUnit(
        taxon=taxon, plant_part="leaf",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="Adults", jurisdiction="EU",
        indication="Sleep and relaxation", route_of_administration="Oral",
    )
    reference = ReferenceDescriptor(
        reference_id=reference_id, source_type="EMA_HMPC", version="v1-test",
        document_date=date(2020, 1, 1),
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="general",
    )
    claim = ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="sleep", assertion_state=AssertionState.PRESENT,
        source_reference_id=reference.reference_id, source_locator="test section 1",
        evidence_text=_evidence_text("Supports sleep.", "test section 1"),
        extraction_confidence=_confidence(),
    )
    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        reference, unit, ReferenceDomain.INDICATION_EVIDENCE,
    )
    case = GoldCase(
        case_id=f"test_case_{normalize_for_id(taxon)}", validation_unit=unit, references=[gref],
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
        engine_evidence=list(engine_evidence),
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def normalize_for_id(taxon: str) -> str:
    return taxon.replace(" ", "_").replace(".", "")


def _exact_dims():
    return (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.POPULATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
    )


def _independent_evidence(taxon):
    return [EngineEvidenceInput(
        scientific_name=taxon, target_indication="Sleep quality",
        notes="An unrelated, independently published trial reported improved sleep outcomes.",
    )]


# ---------------------------------------------------------------------
# 1 & 2 — Melissa with vs without authority suffix
# ---------------------------------------------------------------------

def test_melissa_with_authority_suffix_has_no_collision_signal_today():
    """CORRECTED (see execution_readiness.py's module docstring): an
    authority citation like "L." is not stripped by _norm_taxon, so
    this taxon collides with the seed key under NEITHER normalization
    — a disclosed coverage gap, not a designed protection."""
    case = _build_case("Melissa officinalis L.", engine_evidence=_independent_evidence("Melissa officinalis L."))
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert ReadinessReasonCode.SEED_DATA_COLLISION_RISK not in result.reasons
    assert ReadinessReasonCode.SEED_DATA_COLLISION_CONFIRMED not in result.reasons


def test_melissa_with_trailing_rank_token_is_seed_risk_not_confirmed():
    """A genuinely verified RISK example: a trailing infraspecific-rank
    token with no epithet after it (e.g. "var." alone) IS stripped by
    normalize_taxon(), so it collides with the bare seed key under
    taxon-normalization but not under plain text-normalization."""
    case = _build_case("Melissa officinalis var.", engine_evidence=_independent_evidence("Melissa officinalis var."))
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert ReadinessReasonCode.SEED_DATA_COLLISION_RISK in result.reasons
    assert ReadinessReasonCode.SEED_DATA_COLLISION_CONFIRMED not in result.reasons
    assert result.decision == ExecutionReadiness.DEFER


def test_melissa_without_authority_suffix_is_seed_confirmed():
    case = _build_case("Melissa officinalis", engine_evidence=_independent_evidence("Melissa officinalis"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert ReadinessReasonCode.SEED_DATA_COLLISION_CONFIRMED in result.reasons
    assert ReadinessReasonCode.SEED_DATA_COLLISION_RISK not in result.reasons
    assert result.decision == ExecutionReadiness.BLOCK


# ---------------------------------------------------------------------
# 3 — unrelated non-seed plant
# ---------------------------------------------------------------------

def test_unrelated_non_seed_plant_has_no_collision():
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert ReadinessReasonCode.SEED_DATA_COLLISION_CONFIRMED not in result.reasons
    assert ReadinessReasonCode.SEED_DATA_COLLISION_RISK not in result.reasons


# ---------------------------------------------------------------------
# 4 — no engine evidence
# ---------------------------------------------------------------------

def test_no_engine_evidence_defers():
    case = _build_case("Curcuma longa", engine_evidence=[])
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert ReadinessReasonCode.NO_ENGINE_EVIDENCE in result.reasons
    assert result.decision == ExecutionReadiness.DEFER


# ---------------------------------------------------------------------
# 5 & 6 — preparation / population mismatch
# ---------------------------------------------------------------------

def test_preparation_mismatch_blocks():
    dims = (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.MISMATCH,
                             detail="Evidence concerns a standardized extract, not the case's water infusion."),
        DimensionAssessment(ScopeDimension.POPULATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
    )
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, dims))
    assert ReadinessReasonCode.PREPARATION_MISMATCH in result.reasons
    assert result.decision == ExecutionReadiness.BLOCK


def test_population_mismatch_blocks():
    dims = (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.POPULATION, ScopeEquivalence.MISMATCH,
                             detail="Evidence population is hospitalized burn patients, not the case's general population."),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
    )
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, dims))
    assert ReadinessReasonCode.POPULATION_MISMATCH in result.reasons
    assert result.decision == ExecutionReadiness.BLOCK


# ---------------------------------------------------------------------
# 7 — engine-evidence source overlap with Ground Truth
# ---------------------------------------------------------------------

def test_engine_evidence_source_overlap_blocks():
    reference_id = "EMA_HMPC_196745_2012_test"
    case = _build_case(
        "Curcuma longa",
        reference_id=reference_id,
        engine_evidence=[EngineEvidenceInput(
            scientific_name="Curcuma longa", target_indication="Sleep quality",
            notes=f"Per {reference_id}, this is a traditional-use sleep aid.",
        )],
    )
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert ReadinessReasonCode.ENGINE_EVIDENCE_SOURCE_OVERLAP in result.reasons
    assert result.decision == ExecutionReadiness.BLOCK


# ---------------------------------------------------------------------
# 8 — clean, ready case
# ---------------------------------------------------------------------

def test_clean_ready_case_is_ready():
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert result.decision == ExecutionReadiness.READY
    assert result.reasons == ()


# ---------------------------------------------------------------------
# Additional: dimension not supplied at all is treated as UNKNOWN
# ---------------------------------------------------------------------

def test_missing_dimension_assessment_defers_as_unknown():
    dims = (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.POPULATION, ScopeEquivalence.EXACT),
        # ROUTE intentionally omitted entirely.
    )
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, dims))
    assert ReadinessReasonCode.DIMENSION_UNKNOWN in result.reasons
    assert result.decision == ExecutionReadiness.DEFER


def test_acceptable_equivalence_without_rationale_defers():
    dims = (
        DimensionAssessment(
            ScopeDimension.PREPARATION, ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=None,
        ),
        DimensionAssessment(ScopeDimension.POPULATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
    )
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, dims))
    assert ReadinessReasonCode.EQUIVALENCE_JUSTIFICATION_INCOMPLETE in result.reasons
    assert result.decision == ExecutionReadiness.DEFER


def test_acceptable_equivalence_with_rationale_does_not_defer_on_that_dimension():
    dims = (
        DimensionAssessment(
            ScopeDimension.PREPARATION, ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(
                rationale="Tea-bag brewed as tea is operationally the same category as Infusion.",
            ),
        ),
        DimensionAssessment(ScopeDimension.POPULATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
    )
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    result = assess_execution_readiness(ExecutionReadinessInput(case, dims))
    assert ReadinessReasonCode.EQUIVALENCE_JUSTIFICATION_INCOMPLETE not in result.reasons
    assert result.decision == ExecutionReadiness.READY


# ---------------------------------------------------------------------
# Ground Truth incompleteness (curation_status not lock-eligible)
# ---------------------------------------------------------------------

def test_ground_truth_incomplete_blocks():
    case = _build_case("Curcuma longa", engine_evidence=_independent_evidence("Curcuma longa"))
    case.curation_status = CurationStatus.DRAFT  # not lock-eligible
    result = assess_execution_readiness(ExecutionReadinessInput(case, _exact_dims()))
    assert ReadinessReasonCode.GROUND_TRUTH_INCOMPLETE in result.reasons
    assert result.decision == ExecutionReadiness.BLOCK


# ---------------------------------------------------------------------
# Case 001's actual, expected result — reasoned in the design report,
# now executable. Builds Case 001 exactly as it exists today (no
# engine evidence yet); does NOT run or observe the engine.
# ---------------------------------------------------------------------

def test_case_001_current_expected_readiness_result():
    """CORRECTED expectation (see execution_readiness.py's module
    docstring 'AUTHORITY-CITATION SUFFIXES' limitation): Case 001's
    taxon "Melissa officinalis L." does NOT trigger SEED_DATA_COLLISION
    _RISK under the actual, tested normalization behavior — only
    NO_ENGINE_EVIDENCE fires. An earlier report in this validation
    program's history incorrectly expected a RISK signal here; this
    test asserts the verified, correct result instead."""
    from gold_case_reference_grounded_001_melissa_officinalis import (
        build_gold_case_refgrounded_001_melissa_officinalis_sleep,
    )
    case = build_gold_case_refgrounded_001_melissa_officinalis_sleep()
    result = assess_execution_readiness(ExecutionReadinessInput(case, dimension_assessments=()))

    assert ReadinessReasonCode.NO_ENGINE_EVIDENCE in result.reasons
    assert ReadinessReasonCode.SEED_DATA_COLLISION_RISK not in result.reasons
    assert ReadinessReasonCode.SEED_DATA_COLLISION_CONFIRMED not in result.reasons
    assert ReadinessReasonCode.GROUND_TRUTH_INCOMPLETE not in result.reasons
    assert result.decision == ExecutionReadiness.DEFER


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
