"""
Validation Protocol Execution.

WHAT THIS IS
A bridge between a LOCKED validation_case_protocol.ValidationCaseProtocol
and the existing, completely unmodified BotanicalRDCandidateEngine —
runs the platform against exactly the locked candidate set and
decision context, and returns its raw output. This is the missing
piece that let validation_case_protocol.py define what a locked
protocol IS, without any way to actually run anything against one.

WHAT THIS IS DELIBERATELY NOT
This is NOT scientific validation, and its output is NEVER called
"expected" or "validated" anywhere in this module — it is the
platform's own output for a locked case, to be compared LATER against
a real, independent expert panel's judgment (validation_case_protocol
.ExpertPanel — itself not yet wired to any comparison mechanism; that
remains a separate, future piece of work). Calling this module's
output "validated" would be exactly the kind of overstatement Chapter
7's "implemented with limitations" vocabulary exists to prevent.

WHY THIS IS A SEPARATE MODULE FROM benchmark_harness.py
benchmark_harness.py's case format (rows/similar_groups/evidence/
run_params/expected) is a SELF-REFERENTIAL regression lock: its
"expected" values are captured from a PRIOR run of this same engine,
used to catch unintended behavior changes — its own module docstring
is explicit that this "is not scientific validation, benchmark
calibration, or domain validation." Treating a locked
ValidationCaseProtocol as a benchmark_harness case would silently
conflate those two different things: a scientific protocol prepared
for comparison against real experts is not the same object as a
mechanical snapshot-diff fixture, even though both, in the end, call
BotanicalRDCandidateEngine.run(). This module calls the engine
directly (exactly like benchmark_harness.py's own
_build_engine_for_case() does) rather than routing through
benchmark_harness's case format, so the two concepts never get merged
into one.

WHAT THIS NEVER TOUCHES
This module never imports or modifies botanical_rd_candidate_engine.py
itself — it only calls the existing, public
BotanicalRDCandidateEngine(...).run(...) exactly as
step_rd_candidates.py and benchmark_harness.py already do. No scoring,
ranking, gate, GRADE, or sensitivity logic is read, touched, or
duplicated here.

CANDIDATE SET SCOPING
Per Appendix A, a locked case has a locked candidate set with
documented eligibility rules — the whole point is that ONLY those
candidates are in scope, nothing else. So
execute_protocol_against_engine() FILTERS plant_compounds_df down to
rows whose Scientific_Name is in protocol.candidate_set.candidates
before constructing the engine, rather than running the full
plant_compounds_df and hoping the locked candidates happen to rank
well against an unrelated background set.
"""

from __future__ import annotations

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from validation_case_protocol import ValidationCaseProtocol


class ProtocolNotLockedError(Exception):
    """Raised when execute_protocol_against_engine() is called with a
    protocol that isn't locked. Mirrors
    validation_case_protocol.ProtocolNotReadyError's "never silently
    proceed on an incomplete protocol" guarantee, applied here to
    execution instead of locking — running the engine against an
    unlocked, still-changing candidate set would produce output that
    looks like it came from a locked case when it didn't."""


def execute_protocol_against_engine(
    protocol: ValidationCaseProtocol,
    plant_compounds_df: pd.DataFrame,
    compound_profiles_df: pd.DataFrame = None,
    scientific_evidence_df: pd.DataFrame = None,
    evidence_df: pd.DataFrame = None,
    use_live_search: bool = False,
) -> pd.DataFrame:
    """Runs BotanicalRDCandidateEngine.run() against exactly the
    locked candidate set and decision context of `protocol`. Raises
    ProtocolNotLockedError if the protocol isn't locked, and ValueError
    if the decision context is missing an indication (the one
    Appendix-A-adjacent field DecisionContext.is_locked() does NOT
    require — see that class's own docstring — but the engine cannot
    run without one) or if none of the locked candidates are present
    in plant_compounds_df.

    Returns the engine's raw result_df, completely unmodified — every
    column (R&D_Opportunity_Score, Decision_Class, Gate_Results,
    GRADE_Certainty, etc.) is exactly what
    BotanicalRDCandidateEngine.run() already produces for any other
    caller. See summarize_platform_output() below for a compact,
    protocol-oriented view of this same data.
    """
    if not protocol.locked:
        raise ProtocolNotLockedError(
            f"Cannot execute '{protocol.case_name}': protocol is not locked. "
            f"See validation_case_protocol.lock_protocol()."
        )

    indication = protocol.decision_context.indication
    if not indication:
        raise ValueError(
            f"Cannot execute '{protocol.case_name}': "
            f"decision_context.indication is not set."
        )

    if plant_compounds_df is None or "scientific_name" not in plant_compounds_df.columns:
        raise ValueError(
            "plant_compounds_df must be a DataFrame with a 'scientific_name' column "
            "(lowercase — this is the engine's own input column name; note this is "
            "NOT the same casing as result_df's 'Reference_Plant'/'Alternative_Plant' "
            "output columns)."
        )

    candidate_names = set(protocol.candidate_set.candidates)
    filtered = plant_compounds_df[plant_compounds_df["scientific_name"].isin(candidate_names)]

    if filtered.empty:
        raise ValueError(
            f"None of the locked candidates {sorted(candidate_names)} were found "
            f"in plant_compounds_df's Scientific_Name column for '{protocol.case_name}'."
        )

    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=filtered,
        compound_profiles_df=(
            compound_profiles_df if compound_profiles_df is not None else pd.DataFrame()
        ),
        scientific_evidence_df=(
            scientific_evidence_df if scientific_evidence_df is not None else pd.DataFrame()
        ),
        evidence_df=evidence_df if evidence_df is not None else pd.DataFrame(),
        use_live_search=use_live_search,
    )

    return engine.run(
        indication=indication,
        dosage_form=protocol.decision_context.dosage_form or "",
        market=protocol.decision_context.jurisdiction or "",
    )


def summarize_platform_output(result_df: pd.DataFrame) -> list:
    """A compact, protocol-oriented view of execute_protocol_against_engine()'s
    result — one dict per candidate row, with only the fields relevant
    to comparing against a future expert-panel judgment. Deliberately
    labeled "platform_*" throughout, never "expected"/"validated" — see
    module docstring.

    Returns a list of:
      {"reference_plant": str, "alternative_plant": str,
       "platform_decision_class": str, "platform_decision_class_ah": str,
       "platform_rd_opportunity_score": float,
       "platform_grade_certainty": str}
    """
    if result_df is None or result_df.empty:
        return []

    rows = []
    for _, row in result_df.iterrows():
        rows.append({
            "reference_plant": row.get("Reference_Plant"),
            "alternative_plant": row.get("Alternative_Plant"),
            "platform_decision_class": row.get("Decision_Class"),
            "platform_decision_class_ah": row.get("Decision_Class_AH"),
            "platform_rd_opportunity_score": row.get("R&D_Opportunity_Score"),
            "platform_grade_certainty": row.get("GRADE_Certainty"),
        })
    return rows
