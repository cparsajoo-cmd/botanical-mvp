"""
Validation Architecture v3 — Phase 2: EvaluationRun.

WHAT THIS IS
The record of one official run of a locked-holdout Gold Set against
the real engine — exactly the schema approved in the Phase-1-approval
message: evaluation_run_id, engine_version, gold_set_version,
execution_timestamp, dataset_snapshot_hash. Append-only (see
evaluation_run_persistence.py) — a new evaluation_run_id is generated
every time, never overwritten.

WHAT METRICS THIS COMPUTES (AND WHAT IT DELIBERATELY DOES NOT)
Phase 2 computes two metrics, deliberately not the full metric suite
Validation Architecture v2 named:
  - decision_direction_agreement: proportion metric, POSITIVE/NEGATIVE/
    HOLD/ABSTAIN agreement between ExpectedOutput and the engine's
    actual output (derived via _derive_direction_from_decision_class()).
  - safety_serious_false_negative_rate: proportion metric, restricted
    to RiskStratum.SAFETY_SERIOUS cases — the one release-blocking
    metric named explicitly in the architecture's acceptance criteria.
Gate-level agreement, Top-k inclusion, pairwise agreement, and GRADE
calibration are NOT implemented here — building each properly (especially
Top-k/pairwise, which need multi-candidate comparison cases this
single-taxon execution model does not produce) is real, separate work
deserving its own review, not something to fold silently into this
already-large Phase 2 delivery. This limitation is stated here
explicitly, not left for someone to discover later.

WHY ONLY LOCKED_HOLDOUT CASES ARE ACCEPTED
build_evaluation_run() requires every input GoldCase to be
DatasetSplit.LOCKED_HOLDOUT AND to pass assess_leakage() as
VALID_FOR_HOLDOUT — a QUARANTINED or INVALID_FOR_HOLDOUT case raises
rather than being silently excluded, so a caller cannot accidentally
produce an "official" evaluation run over a partially-contaminated
set without finding out.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from dataset_canonicalization import hash_dataset
from dataset_split import DatasetSplit, LeakageAssessment, assess_leakage
from gold_case import GoldCase, RiskStratum, DecisionDirection
from gold_case_execution import execute_gold_case_against_engine, platform_output_for_gold_case, GoldCaseNotExecutableError
from metric_report import build_proportion_metric, MetricReport


class EvaluationRunError(Exception):
    """Raised when build_evaluation_run() cannot proceed — e.g. a
    non-holdout or leakage-tainted case in the input set. Never
    silently drops a case; always fails loudly so the caller must fix
    the input set rather than get a silently-partial run."""


@dataclass
class EvaluationRun:
    evaluation_run_id: str
    engine_version: str
    gold_set_version: str
    execution_timestamp: datetime
    dataset_snapshot_hash: str
    dataset_split_used: str  # always "Locked holdout" in Phase 2
    results: list = field(default_factory=list)  # list[MetricReport]
    case_count: int = 0
    inexecutable_case_ids: list = field(default_factory=list)  # cases that raised GoldCaseNotExecutableError


_POSITIVE_DECISION_CLASSES = {
    "Strong R&D candidate",
    "Promising candidate; verify safety and standardization",
    "Early-stage candidate; more evidence needed",
}
_NEGATIVE_DECISION_CLASSES = {
    "Safety concern — not suitable without expert review",
    "Regulatory prohibition — not suitable without regulatory review",
}
_HOLD_DECISION_CLASSES = {
    "Low priority / insufficient data",
}


def _derive_direction_from_decision_class(decision_class: Optional[str]) -> Optional[DecisionDirection]:
    """Maps the engine's own Decision_Class vocabulary onto
    DecisionDirection. Returns None (not a guessed default) for an
    unrecognized or missing Decision_Class — an unrecognized value is
    a data problem to surface, never silently classified as HOLD."""
    if decision_class in _POSITIVE_DECISION_CLASSES:
        return DecisionDirection.POSITIVE
    if decision_class in _NEGATIVE_DECISION_CLASSES:
        return DecisionDirection.NEGATIVE
    if decision_class in _HOLD_DECISION_CLASSES:
        return DecisionDirection.HOLD
    return None


def _new_evaluation_run_id() -> str:
    return str(uuid.uuid4())


def _resolve_engine_version() -> str:
    import botanical_rd_candidate_engine as eng
    return eng.DECISION_ENGINE_VERSION


def build_evaluation_run(
    gold_cases: list,
    gold_set_version: str = "unspecified",
    engine_version: Optional[str] = None,
    evaluation_run_id: Optional[str] = None,
) -> EvaluationRun:
    """Executes every LOCKED_HOLDOUT GoldCase in `gold_cases` against
    the real engine (via gold_case_execution.py — no stubbing) and
    computes the two Phase 2 metrics (see module docstring). Raises
    EvaluationRunError if any input case is not LOCKED_HOLDOUT or does
    not pass assess_leakage() as VALID_FOR_HOLDOUT.

    A GoldCase that raises GoldCaseNotExecutableError (e.g. missing
    dosage_form) is recorded in inexecutable_case_ids and excluded
    from metric denominators — this is NOT the same as a leakage
    failure; an inexecutable case is a data-completeness issue on the
    case itself, disclosed in the returned EvaluationRun rather than
    silently dropped without a trace.
    """
    for case in gold_cases:
        if case.dataset_split != DatasetSplit.LOCKED_HOLDOUT:
            raise EvaluationRunError(
                f"GoldCase {case.case_id!r} is not LOCKED_HOLDOUT "
                f"(found {case.dataset_split.value!r}) — cannot be part of an EvaluationRun."
            )
        leak = assess_leakage(case.case_id, case.dataset_split, case.leakage_control)
        if leak.assessment != LeakageAssessment.VALID_FOR_HOLDOUT:
            raise EvaluationRunError(
                f"GoldCase {case.case_id!r} failed leakage assessment "
                f"({leak.assessment.value}): {leak.reason}"
            )

    inexecutable_case_ids = []
    direction_pairs = []  # (expected, actual) for decision_direction_agreement
    safety_serious_pairs = []  # (expected, actual) restricted to SAFETY_SERIOUS stratum

    for case in gold_cases:
        try:
            result_df = execute_gold_case_against_engine(case)
        except GoldCaseNotExecutableError:
            inexecutable_case_ids.append(case.case_id)
            continue

        output = platform_output_for_gold_case(result_df)
        actual_direction = _derive_direction_from_decision_class(output.get("decision_class"))
        expected_direction = case.expected_output.expected_decision_direction

        if expected_direction is not None and actual_direction is not None:
            direction_pairs.append((expected_direction, actual_direction))

        if RiskStratum.SAFETY_SERIOUS in case.risk_strata:
            if expected_direction is not None and actual_direction is not None:
                safety_serious_pairs.append((expected_direction, actual_direction))

    direction_numerator = sum(1 for e, a in direction_pairs if e == a)
    direction_denominator = len(direction_pairs)
    direction_metric = build_proportion_metric(
        "decision_direction_agreement", direction_numerator, direction_denominator,
        detail="Agreement between GoldCase.expected_output.expected_decision_direction and the engine's actual derived direction.",
    )

    # False negative: expected NEGATIVE (a real safety stop was
    # expected) but the engine did NOT produce NEGATIVE.
    safety_fn_numerator = sum(
        1 for e, a in safety_serious_pairs if e == DecisionDirection.NEGATIVE and a != DecisionDirection.NEGATIVE
    )
    safety_fn_denominator = sum(1 for e, a in safety_serious_pairs if e == DecisionDirection.NEGATIVE)
    safety_fn_metric = build_proportion_metric(
        "safety_serious_false_negative_rate", safety_fn_numerator, safety_fn_denominator,
        detail="Release-blocking metric — must be exactly 0 for any production release profile.",
    )

    return EvaluationRun(
        evaluation_run_id=evaluation_run_id or _new_evaluation_run_id(),
        engine_version=engine_version or _resolve_engine_version(),
        gold_set_version=gold_set_version,
        execution_timestamp=datetime.now(timezone.utc),
        dataset_snapshot_hash=hash_dataset(gold_cases),
        dataset_split_used=DatasetSplit.LOCKED_HOLDOUT.value,
        results=[direction_metric, safety_fn_metric],
        case_count=len(gold_cases),
        inexecutable_case_ids=inexecutable_case_ids,
    )
