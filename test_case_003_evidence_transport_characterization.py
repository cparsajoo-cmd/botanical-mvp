"""
Characterization test — Case 003 evidence-transport investigation.

WHAT THIS RECORDS, AND WHY IT EXISTS
This file originally recorded the PRE-FIX behavior of
gold_case_execution.py: GoldCase.engine_evidence and the `evidence=`
parameter accepted by execute_gold_case_against_engine()/
execute_gold_case_with_readiness_gate() were two independent channels,
neither kept in sync with the other, which is why
case_003_engine_evidence_run.py's first real execution reported "no
direct evidence" despite EngineEvidenceInput.notes containing real
text (see conversation record for the full characterization report).

gold_case_execution.py has SINCE BEEN CORRECTED (the evidence-channel-
unification fix: _resolve_effective_evidence() +
execute_gold_case_with_readiness_gate() now compute one effective
evidence value and pass it to both the readiness guard and the
engine). Test 1 below is unaffected by that fix (it calls
execute_gold_case_against_engine() directly, whose own contract never
changed — evidence is, and always was, only ever its own explicit
parameter). Tests 2 and 3 exercise the WRAPPER and have been updated
to assert its current, corrected behavior; their docstrings note what
used to be true before the fix, for historical traceability.

Neither this file nor its execution modifies botanical_rd_candidate_
engine.py, or Case 003's frozen Ground Truth file.
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
    """STILL TRUE AFTER THE FIX — this function's own contract never
    changed. execute_gold_case_against_engine() (called directly, not
    through the wrapper) reads only its own `evidence` parameter,
    never gold_case.engine_evidence — by design, documented in its own
    docstring. Calling it directly with evidence=None still ignores a
    populated GoldCase.engine_evidence field. The unification fix
    lives in the WRAPPER (execute_gold_case_with_readiness_gate()),
    which now computes the effective evidence before calling this
    lower-level function — see tests below."""
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


def test_evidence_passed_only_via_parameter_now_reaches_execution_after_the_fix():
    """UPDATED after the evidence-channel-unification fix.
    BEFORE THE FIX, this exact call (evidence passed only via the
    `evidence=` parameter, GoldCase.engine_evidence left empty)
    returned DEFER/NO_ENGINE_EVIDENCE without ever reaching the
    engine — because the guard checked only GoldCase.engine_evidence.
    AFTER THE FIX: _resolve_effective_evidence() sees evidence is not
    None and gold_case.engine_evidence is empty, so it uses the
    explicit evidence for BOTH the readiness check and the engine
    call — this now reaches READY and a real PASSED gate."""
    case = build_gold_case_refgrounded_003_matricaria_chamomilla_sleep()
    evidence = _evidence()
    dimension_assessments = (
        DimensionAssessment(ScopeDimension.PREPARATION, ScopeEquivalence.EXACT),
        DimensionAssessment(ScopeDimension.ROUTE, ScopeEquivalence.EXACT),
        DimensionAssessment(
            ScopeDimension.POPULATION, ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(rationale="Test fixture only — not Case 003's real judgment."),
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

    assert readiness.decision.value == "Ready", readiness.reasons
    assert result_df is not None
    gate = result_df.iloc[0]["Gate_Results"]["minimum_evidence"]
    assert gate["status"].value == "passed"
    assert gate["evidence"] == "Clinical / human evidence"


def test_identical_evidence_on_both_channels_remains_supported():
    """Verifies that supplying identical evidence through BOTH
    GoldCase.engine_evidence and the explicit evidence= parameter
    resolves to one effective evidence value and executes correctly —
    NOT because both channels are required (they aren't; either one
    alone is sufficient, see the other tests in this file and in
    test_gold_case_execution_evidence_channel.py), but because
    supplying the same content on both must remain a valid, supported
    pattern, not treated as a conflict."""
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
        test_evidence_passed_only_via_parameter_now_reaches_execution_after_the_fix,
        test_identical_evidence_on_both_channels_remains_supported,
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
