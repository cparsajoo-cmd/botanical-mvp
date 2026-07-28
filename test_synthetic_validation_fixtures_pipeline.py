"""
Fixture-pipeline tests for Validation Architecture v3, Phase 1.

WHAT THIS COVERS
The full Phase 1 pipeline — applicability, precedence, leakage
assessment, metric reporting — run end to end against
synthetic_validation_fixtures.fixtures's synthetic cases. Confirms the
modules compose correctly together, not just in isolation.

WHAT THIS DELIBERATELY DOES NOT DO (v3 correction #3)
No real BotanicalRDCandidateEngine execution anywhere in this file —
the GoldCase-to-ValidationCaseProtocol bridge and
execute_protocol_against_engine() integration are explicitly Phase 2
scope. Every "engine output" referenced here is the case's own curated
ExpectedOutput or a structured fake, never a real engine run.
"""

from applicability_check import check_applicability, ReferenceDomain
from dataset_split import assess_leakage, move_to_development, LeakageAssessment, DatasetSplit
from metric_report import build_proportion_metric, MetricStatus
from reference_precedence import resolve_precedence, ResolutionStatus
from synthetic_validation_fixtures.fixtures import build_synthetic_gold_cases


def test_fixture_set_has_at_least_one_case_per_major_stratum():
    cases = build_synthetic_gold_cases()
    all_strata = {s for case in cases for s in case.risk_strata}
    from gold_case import RiskStratum
    assert RiskStratum.CLEAN_BASELINE in all_strata
    assert RiskStratum.SAFETY_SERIOUS in all_strata
    assert RiskStratum.PREPARATION_MISMATCH in all_strata
    assert RiskStratum.CONFLICTING_EVIDENCE in all_strata
    assert RiskStratum.NO_REFERENCE in all_strata


def test_all_case_ids_are_prefixed_synthetic():
    # Guards against a future real Gold Set accidentally being added
    # to this same fixtures module.
    for case in build_synthetic_gold_cases():
        assert case.case_id.startswith("synthetic_")


def test_clean_baseline_case_resolves_to_selected():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_clean_baseline_001"]
    pairs = []
    for gref in case.references:
        result = check_applicability(gref.reference, case.validation_unit, ReferenceDomain.SAFETY)
        if result.applicable and gref.verdict:
            pairs.append((gref.reference, gref.verdict))
    resolution = resolve_precedence(ReferenceDomain.SAFETY, pairs)
    assert resolution.status == ResolutionStatus.SELECTED


def test_safety_serious_case_selects_the_more_severe_reference():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_safety_serious_001"]
    pairs = []
    for gref in case.references:
        result = check_applicability(gref.reference, case.validation_unit, ReferenceDomain.SAFETY)
        if result.applicable and gref.verdict:
            pairs.append((gref.reference, gref.verdict))
    resolution = resolve_precedence(ReferenceDomain.SAFETY, pairs)
    assert resolution.status == ResolutionStatus.SELECTED
    assert resolution.selected_reference_id == "synthetic_ref_safety_serious"


def test_preparation_mismatch_case_has_no_applicable_reference():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_preparation_mismatch_001"]
    gref = case.references[0]
    result = check_applicability(gref.reference, case.validation_unit, ReferenceDomain.SAFETY)
    assert result.applicable is False
    from applicability_check import ApplicabilityDimension
    assert ApplicabilityDimension.PREPARATION in result.failed_dimensions


def test_conflicting_evidence_case_resolves_to_reference_conflict_in_its_domain():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_conflicting_evidence_001"]
    pairs = []
    for gref in case.references:
        result = check_applicability(gref.reference, case.validation_unit, ReferenceDomain.INDICATION_EVIDENCE)
        if result.applicable and gref.verdict:
            pairs.append((gref.reference, gref.verdict))
    resolution = resolve_precedence(ReferenceDomain.INDICATION_EVIDENCE, pairs)
    assert resolution.status == ResolutionStatus.REFERENCE_CONFLICT


def test_no_reference_case_resolves_to_no_applicable_reference():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_no_reference_001"]
    assert case.references == []
    resolution = resolve_precedence(ReferenceDomain.SAFETY, [])
    assert resolution.status == ResolutionStatus.NO_APPLICABLE_REFERENCE


def test_no_reference_case_is_marked_correct_abstention_expected():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_no_reference_001"]
    assert case.correct_abstention_expected is True


# ---------------------------------------------------------------------
# Leakage pipeline
# ---------------------------------------------------------------------

def test_clean_holdout_case_is_valid():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_locked_holdout_clean_001"]
    assert case.dataset_split == DatasetSplit.LOCKED_HOLDOUT
    result = assess_leakage(case.case_id, case.dataset_split, case.leakage_control)
    assert result.assessment == LeakageAssessment.VALID_FOR_HOLDOUT


def test_leaked_holdout_case_is_invalid_and_can_be_moved():
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    case = cases["synthetic_locked_holdout_leaked_001"]
    result = assess_leakage(case.case_id, case.dataset_split, case.leakage_control)
    assert result.assessment == LeakageAssessment.INVALID_FOR_HOLDOUT

    # dataset_split on the original case object is UNCHANGED by
    # assessment alone (v3 correction #7) — only the explicit move
    # operation changes it.
    assert case.dataset_split == DatasetSplit.LOCKED_HOLDOUT

    new_split, audit = move_to_development(case.case_id, case.dataset_split, result.reason)
    assert new_split == DatasetSplit.DEVELOPMENT
    assert audit.case_id == case.case_id


# ---------------------------------------------------------------------
# Metric reporting over the fixture set (using curated ExpectedOutput
# as a stand-in "reference truth" and a STRUCTURED FAKE "engine output"
# — never a real engine call, per v3 correction #3)
# ---------------------------------------------------------------------

def test_metric_report_over_fixture_set_using_fake_engine_output():
    from gold_case import DecisionDirection

    cases = build_synthetic_gold_cases()

    # A structured fake standing in for "what the engine said" —
    # deliberately hand-written per case_id, never derived from a real
    # engine run (Phase 1 scope boundary).
    fake_engine_output = {
        "synthetic_clean_baseline_001": DecisionDirection.POSITIVE,   # agrees
        "synthetic_safety_serious_001": DecisionDirection.NEGATIVE,   # agrees
        "synthetic_preparation_mismatch_001": DecisionDirection.ABSTAIN,  # agrees
        "synthetic_conflicting_evidence_001": DecisionDirection.POSITIVE,  # DISAGREES (expected HOLD)
        "synthetic_no_reference_001": DecisionDirection.ABSTAIN,      # agrees
    }

    numerator = 0
    denominator = 0
    for case in cases:
        expected = case.expected_output.expected_decision_direction
        actual = fake_engine_output.get(case.case_id)
        if expected is None or actual is None:
            continue
        denominator += 1
        if expected == actual:
            numerator += 1

    report = build_proportion_metric("direction_agreement", numerator, denominator)
    assert report.status == MetricStatus.COMPUTED
    assert report.proportion.numerator == 4
    assert report.proportion.denominator == 5
    assert report.proportion.point_estimate == 0.8


def test_metric_report_not_computable_when_no_cases_have_expected_output():
    report = build_proportion_metric("direction_agreement", 0, 0)
    assert report.status == MetricStatus.NOT_COMPUTABLE


def test_fixture_pipeline_never_imports_the_real_engine():
    # Static guard: this test file, and the fixtures module it
    # exercises, must not import botanical_rd_candidate_engine or
    # validation_protocol_execution — those are Phase 2.
    import inspect
    import synthetic_validation_fixtures.fixtures as fixtures_module

    source = inspect.getsource(fixtures_module)
    assert "botanical_rd_candidate_engine" not in source
    assert "execute_protocol_against_engine" not in source
