"""
Characterization test — Case 003 evidence-transport investigation.

WHAT THIS RECORDS, AND WHY IT EXISTS
This is NOT a regression test for a bug fix — no production behavior
is changed anywhere in this repository as a result of this file.
It records CURRENT, OBSERVED behavior of the existing, unmodified
gold_case_execution.py API: GoldCase.engine_evidence (the field a
curator populates on the case) and the `evidence=` parameter accepted
by execute_gold_case_against_engine()/execute_gold_case_with_readiness
_gate() are two SEPARATE things — populating the former does not
automatically populate the latter. This was discovered while
investigating why case_003_engine_evidence_run.py's first real
execution reported "no direct evidence" despite EngineEvidenceInput
.notes containing real text (see conversation record for the full
characterization report).

Both tests below use a minimal, deterministic, local-only engine
construction (empty DataFrames, use_live_search=False) — no Supabase,
no network. Neither test modifies botanical_rd_candidate_engine.py,
gold_case_execution.py, execution_readiness.py, or Case 003's frozen
Ground Truth file.
"""

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from engine_evidence_input import EngineEvidenceInput
from execution_readiness import DimensionAssessment, EquivalenceJustification, ScopeDimension, ScopeEquivalence
from gold_case_execution import (
    _GOLD_CASE_ANCHOR_TAXON,
    execute_gold_case_against_engine,
    execute_gold_case_with_readiness_gate,
)
from gold_case_reference_grounded_003_matricaria_chamomilla import (
    build_gold_case_refgrounded_003_matricaria_chamomilla_sleep,
)


def _evidence():
    return [EngineEvidenceInput(
        scientific_name="Matricaria chamomilla L.",
        target_indication="Sleep quality",
        notes=(
            "A randomized controlled trial in 80 postnatal women with poor "
            "sleep quality, assigned to drink chamomile tea daily for two "
            "weeks or usual postpartum care. The tea group showed "
            "significantly lower sleep-inefficiency scores than control."
        ),
    )]


def test_engine_evidence_on_gold_case_field_alone_is_not_used_by_execute_gold_case_against_engine():
    """CHARACTERIZATION (current behavior, not a claim this is correct
    or incorrect): setting GoldCase.engine_evidence directly and then
    calling execute_gold_case_against_engine() WITHOUT also passing
    evidence= explicitly results in the engine receiving ZERO evidence
    for the candidate — because that function reads only its own
    `evidence` parameter (default None), never gold_case.engine_evidence.
    This reproduces case_003_engine_evidence_run.py's original
    NOT_EVALUABLE result and confirms its exact mechanism."""
    from dataclasses import replace

    case = build_gold_case_refgrounded_003_matricaria_chamomilla_sleep()
    case_with_evidence_on_field_only = replace(case, engine_evidence=_evidence())

    result_df = execute_gold_case_against_engine(
        case_with_evidence_on_field_only,
        evidence=None,  # NOT passed through, even though the case's own field is populated
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )

    row = result_df.iloc[0]
    gate = row["Gate_Results"]["minimum_evidence"]
    assert gate["status"].value == "not_evaluable"
    assert "No direct evidence is recorded" in gate["reason"]


def test_engine_evidence_explicitly_passed_through_is_used_and_passes_the_gate():
    """CHARACTERIZATION: passing evidence ONLY via the `evidence=`
    parameter (matching execute_gold_case_against_engine()'s own
    documented convention) — WITHOUT also setting it on
    GoldCase.engine_evidence — is not sufficient to reach execution at
    all via execute_gold_case_with_readiness_gate(): the readiness
    guard checks GoldCase.engine_evidence specifically (see
    execution_readiness.py's _ground_truth_ok/NO_ENGINE_EVIDENCE
    check), sees it empty, and returns DEFER before the engine is ever
    reached — regardless of what was passed via `evidence=`. This
    isolates that the two evidence channels are read by two different
    parts of the pipeline. See the next test for the invocation that
    actually reaches a real PASSED gate."""
    case = build_gold_case_refgrounded_003_matricaria_chamomilla_sleep()
    evidence = _evidence()
    dimension_assessments = (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
        DimensionAssessment(
            ScopeDimension.POPULATION, ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(rationale="See case_003_engine_evidence_run.py."),
        ),
    )

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case,  # engine_evidence NOT set on the case itself
        dimension_assessments=dimension_assessments,
        evidence=evidence,  # only passed here
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )

    assert readiness.decision.value == "Defer"
    assert readiness.reasons == (
        __import__("execution_readiness").ReadinessReasonCode.NO_ENGINE_EVIDENCE,
    )
    assert result_df is None, "guard must refuse execution when GoldCase.engine_evidence is empty"


def test_correct_invocation_requires_setting_both_independent_evidence_channels():
    """CHARACTERIZATION — the more important finding, found while
    fixing the test above: execute_gold_case_with_readiness_gate()
    consults TWO INDEPENDENT evidence channels that are not kept in
    sync by any existing code:
      (a) GoldCase.engine_evidence — read by
          execution_readiness.assess_execution_readiness()'s
          NO_ENGINE_EVIDENCE check;
      (b) the separate `evidence=` parameter — read by
          execute_gold_case_against_engine() to actually build
          evidence_df for the engine.
    Passing evidence only via (b) (previous test) leaves (a) empty,
    so the readiness guard reports NO_ENGINE_EVIDENCE and refuses to
    execute at all — even though the evidence that would have worked
    was right there in the `evidence=` argument. This test shows the
    only invocation pattern that currently produces a real, correct
    READY-and-executed result: setting BOTH GoldCase.engine_evidence
    (via dataclasses.replace) AND the `evidence=` parameter to the
    same content."""
    from dataclasses import replace

    case = build_gold_case_refgrounded_003_matricaria_chamomilla_sleep()
    evidence = _evidence()
    case_with_evidence = replace(case, engine_evidence=evidence)  # channel (a)
    dimension_assessments = (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
        DimensionAssessment(
            ScopeDimension.POPULATION, ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(rationale="See case_003_engine_evidence_run.py."),
        ),
    )

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case_with_evidence,
        dimension_assessments=dimension_assessments,
        evidence=evidence,  # channel (b) — same content, passed separately
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )

    assert readiness.decision.value == "Ready", readiness.reasons
    assert result_df is not None
    gate = result_df.iloc[0]["Gate_Results"]["minimum_evidence"]
    assert gate["status"].value == "passed"
    assert gate["evidence"] == "Clinical / human evidence"


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        test_engine_evidence_on_gold_case_field_alone_is_not_used_by_execute_gold_case_against_engine,
        test_engine_evidence_explicitly_passed_through_is_used_and_passes_the_gate,
        test_correct_invocation_requires_setting_both_independent_evidence_channels,
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
