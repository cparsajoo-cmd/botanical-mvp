"""
Fixture-pipeline tests for Reference-Grounded Validation (v4).

WHAT THIS COVERS
The full v4 pipeline — claims, applicability, resolve_expected_outcomes,
is_lockable/lock_gold_case, leakage assessment, metric reporting — run
end to end against synthetic_validation_fixtures.fixtures's synthetic
cases.

WHAT THIS DELIBERATELY DOES NOT DO
No real BotanicalRDCandidateEngine execution in THIS file — the real
engine is exercised in test_gold_case_execution.py and
test_evaluation_run.py instead. This file covers the claim ->
resolved-outcome -> lock pipeline composing correctly, independent of
engine execution.
"""

from applicability_check import ReferenceDomain
from dataset_split import assess_leakage, move_to_development, LeakageAssessment, DatasetSplit
from gold_case import RiskStratum, is_lockable
from reference_precedence import ResolutionStatus
from resolved_expected_outcome import resolve_expected_outcomes
from synthetic_validation_fixtures.fixtures import build_synthetic_gold_cases


def test_fixture_set_has_at_least_one_case_per_major_stratum():
    cases = build_synthetic_gold_cases()
    all_strata = {s for case in cases for s in case.risk_strata}
    assert RiskStratum.CLEAN_BASELINE in all_strata
    assert RiskStratum.SAFETY_SERIOUS in all_strata
    assert RiskStratum.PREPARATION_MISMATCH in all_strata
    assert RiskStratum.CONFLICTING_EVIDENCE in all_strata
    assert RiskStratum.NO_REFERENCE in all_strata


def test_all_case_ids_are_prefixed_synthetic():
    for case in build_synthetic_gold_cases():
        assert case.case_id.startswith("synthetic_")


def test_all_fixtures_are_explicitly_marked_synthetic_kind():
    from assertion_vocabulary import GoldCaseKind
    for case in build_synthetic_gold_cases():
        assert case.kind == GoldCaseKind.SYNTHETIC


def test_clean_baseline_case_resolved_outcome_is_selected():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_clean_baseline_001"]
    assert len(case.resolved_outcomes) == 1
    assert case.resolved_outcomes[0].resolution_status == ResolutionStatus.SELECTED


def test_clean_baseline_case_is_lockable():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_clean_baseline_001"]
    ok, reasons = is_lockable(case)
    assert ok is True
    assert reasons == []


def test_safety_serious_case_resolved_outcome_selects_serious_severity():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_safety_serious_001"]
    assert len(case.resolved_outcomes) == 1
    outcome = case.resolved_outcomes[0]
    assert outcome.resolution_status == ResolutionStatus.SELECTED
    from assertion_vocabulary import SeverityLevel
    assert outcome.severity == SeverityLevel.SERIOUS


def test_safety_serious_case_is_lockable():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_safety_serious_001"]
    ok, reasons = is_lockable(case)
    assert ok is True


def test_preparation_mismatch_case_has_no_applicable_reference():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_preparation_mismatch_001"]
    gref = case.references[0]
    result = gref.applicability_by_domain[ReferenceDomain.SAFETY]
    assert result.applicable is False
    from applicability_check import ApplicabilityDimension
    assert ApplicabilityDimension.PREPARATION in result.failed_dimensions


def test_preparation_mismatch_case_resolved_outcome_is_no_applicable_reference():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_preparation_mismatch_001"]
    assert case.resolved_outcomes[0].resolution_status == ResolutionStatus.NO_APPLICABLE_REFERENCE


def test_preparation_mismatch_case_cannot_lock():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_preparation_mismatch_001"]
    ok, reasons = is_lockable(case)
    assert ok is False


def test_conflicting_evidence_case_resolves_to_reference_conflict():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_conflicting_evidence_001"]
    assert case.resolved_outcomes[0].resolution_status == ResolutionStatus.REFERENCE_CONFLICT


def test_conflicting_evidence_case_cannot_lock():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_conflicting_evidence_001"]
    ok, reasons = is_lockable(case)
    assert ok is False
    assert any("Reference conflict" in r for r in reasons)


def test_no_reference_case_has_empty_resolved_outcomes():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_no_reference_001"]
    assert case.references == []
    assert case.resolved_outcomes == []


def test_no_reference_case_cannot_lock():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_no_reference_001"]
    ok, reasons = is_lockable(case)
    assert ok is False


def test_no_reference_case_is_marked_correct_abstention_expected():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_no_reference_001"]
    assert case.correct_abstention_expected is True


# ---------------------------------------------------------------------
# Leakage pipeline
# ---------------------------------------------------------------------

def test_clean_holdout_case_is_already_locked():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_locked_holdout_clean_001"]
    assert case.dataset_split == DatasetSplit.LOCKED_HOLDOUT
    assert case.locked is True
    assert case.dataset_snapshot_hash is not None


def test_clean_holdout_case_is_valid_for_holdout():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_locked_holdout_clean_001"]
    result = assess_leakage(case.case_id, case.dataset_split, case.leakage_control)
    assert result.assessment == LeakageAssessment.VALID_FOR_HOLDOUT


def test_leaked_holdout_case_is_invalid_and_can_be_moved():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_locked_holdout_leaked_001"]
    result = assess_leakage(case.case_id, case.dataset_split, case.leakage_control)
    assert result.assessment == LeakageAssessment.INVALID_FOR_HOLDOUT

    # dataset_split on the original case object is UNCHANGED by
    # assessment alone.
    assert case.dataset_split == DatasetSplit.LOCKED_HOLDOUT

    new_split, audit = move_to_development(case.case_id, case.dataset_split, result.reason)
    assert new_split == DatasetSplit.DEVELOPMENT
    assert audit.case_id == case.case_id


def test_fixture_pipeline_never_imports_the_real_engine():
    import inspect
    import synthetic_validation_fixtures.fixtures as fixtures_module

    source = inspect.getsource(fixtures_module)
    assert "botanical_rd_candidate_engine" not in source
    assert "execute_gold_case_against_engine" not in source
