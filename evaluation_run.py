"""
Reference-Grounded Validation — EvaluationRun.

WHAT THIS IS
The record of one official run of a locked-holdout Gold Set against
the real engine: evaluation_run_id, engine_version, gold_set_version,
execution_timestamp, dataset_snapshot_hash, validation_scope.
Append-only (see evaluation_run_persistence.py) — a new
evaluation_run_id is generated every time, never overwritten.

PROVIDED-EVIDENCE VALIDATION, NOT END-TO-END (v4 correction #6/#8)
validation_scope is ALWAYS ValidationScope.PROVIDED_EVIDENCE in this
module — build_evaluation_run() has no parameter that could set it to
END_TO_END, and EvaluationRun's own __post_init__ raises if anyone
constructs one with END_TO_END directly. This is not because
END_TO_END is unsupportable in principle (see ValidationScope's own
docstring — it is a real, reserved value for the future Corpus/
Retrieval Validation phase) but because THIS module supplies the
correct source evidence directly to the engine (via
GoldCase.engine_evidence) rather than having the engine retrieve it —
so what this module validates is extraction, interpretation, gates,
and decision translation, never retrieval. Every EvaluationRun this
module produces should be read as: "the engine, given the correct
evidence, produced the correct interpretation" — not "the engine would
have found this evidence on its own."

WHAT METRICS THIS COMPUTES (AND WHAT IT DELIBERATELY DOES NOT)
  - decision_direction_agreement: proportion metric, POSITIVE/NEGATIVE/
    HOLD/ABSTAIN agreement between GoldCase.expected_output (a
    simplified, human-curated summary field — see gold_case.py) and
    the engine's actual derived direction. AS OF THE Prospective
    Claim-to-Decision Mapping Proposal (Phase 3): only cases assessed
    ELIGIBLE by agreement_eligibility.assess_agreement_eligibility()
    contribute to this metric's numerator/denominator — see
    EvaluationRun.agreement_eligibility below for the full,
    never-silent record of why any given case was or wasn't included.
  - safety_serious_false_negative_rate: proportion metric, computed
    against GoldCase.resolved_outcomes (the FINAL Reference-Grounded
    Validation truth — see resolved_expected_outcome.py), restricted
    to SAFETY-domain, SERIOUS-severity, PRESENT-state outcomes. This
    is the release-blocking metric named explicitly in the
    architecture's acceptance criteria, and the one that actually
    reflects the new ReferenceClaim -> ResolvedExpectedOutcome
    pipeline, not a simplified per-case label. UNAFFECTED by the
    Phase 3 addition — this metric never used expected_output/
    DecisionDirection in the first place.
Gate-level agreement, Top-k inclusion, pairwise agreement, and GRADE
calibration are NOT implemented here — real, separate work.

WHY ONLY LOCKED_HOLDOUT CASES ARE ACCEPTED
build_evaluation_run() requires every input GoldCase to be
DatasetSplit.LOCKED_HOLDOUT, locked=True, AND to pass assess_leakage()
as VALID_FOR_HOLDOUT.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from assertion_vocabulary import (
    AssertionState, AssertionType, SeverityLevel, ValidationScope,
)
from applicability_check import ReferenceDomain
from dataset_canonicalization import hash_dataset
from dataset_split import DatasetSplit, LeakageAssessment, assess_leakage
from gold_case import GoldCase, DecisionDirection
from gold_case_execution import execute_gold_case_against_engine, platform_output_for_gold_case, GoldCaseNotExecutableError
from metric_report import build_proportion_metric, MetricReport
from reference_precedence import ResolutionStatus
from agreement_eligibility import AgreementEligibility, assess_agreement_eligibility


class EvaluationRunError(Exception):
    """Raised when build_evaluation_run() cannot proceed — e.g. a
    non-holdout, unlocked, or leakage-tainted case in the input set."""


class InvalidValidationScopeError(Exception):
    """Raised if an EvaluationRun is ever constructed with
    ValidationScope.END_TO_END — not yet supported by any module in
    this repository (v4 correction #6/#8)."""


@dataclass
class EvaluationRun:
    evaluation_run_id: str
    engine_version: str
    gold_set_version: str
    execution_timestamp: datetime
    dataset_snapshot_hash: str
    dataset_split_used: str  # always "Locked holdout"
    validation_scope: ValidationScope = ValidationScope.PROVIDED_EVIDENCE
    results: list = field(default_factory=list)  # list[MetricReport]
    case_count: int = 0
    inexecutable_case_ids: list = field(default_factory=list)
    # Phase 3 addition (Prospective Claim-to-Decision Mapping Proposal).
    # case_id -> AgreementEligibilityResult, for EVERY executable case,
    # both ELIGIBLE and NOT_ELIGIBLE — never a silent omission. Empty
    # dict by default so any existing code constructing an
    # EvaluationRun without this field (or reading one built before
    # this field existed) is unaffected — backward compatible.
    agreement_eligibility: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.validation_scope != ValidationScope.PROVIDED_EVIDENCE:
            raise InvalidValidationScopeError(
                f"EvaluationRun.validation_scope must be PROVIDED_EVIDENCE in this "
                f"module — got {self.validation_scope!r}. END_TO_END is reserved for "
                f"a future Corpus/Retrieval Validation phase, not yet implemented."
            )


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
    DecisionDirection. Returns None for an unrecognized/missing value
    — never silently guessed."""
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


def _is_expected_serious_safety_present(outcome) -> bool:
    return (
        outcome.domain == ReferenceDomain.SAFETY
        and outcome.resolution_status == ResolutionStatus.SELECTED
        and outcome.severity == SeverityLevel.SERIOUS
        and outcome.assertion_state == AssertionState.PRESENT
    )


def build_evaluation_run(
    gold_cases: list,
    gold_set_version: str = "unspecified",
    engine_version: Optional[str] = None,
    evaluation_run_id: Optional[str] = None,
) -> EvaluationRun:
    """Executes every LOCKED_HOLDOUT GoldCase in `gold_cases` against
    the real engine — via gold_case_execution.py, fed exclusively with
    case.engine_evidence (never case.references[].claims; see
    gold_case.py's own structural-separation docstring) — and computes
    the two metrics documented in this module's docstring.

    Raises EvaluationRunError if any input case is not LOCKED_HOLDOUT,
    is not locked, or does not pass assess_leakage() as
    VALID_FOR_HOLDOUT.

    A GoldCase that raises GoldCaseNotExecutableError is recorded in
    inexecutable_case_ids and excluded from metric denominators.

    Every case that DOES execute gets an explicit
    agreement_eligibility.AgreementEligibilityResult recorded in the
    returned EvaluationRun.agreement_eligibility dict — ELIGIBLE cases
    contribute to decision_direction_agreement; NOT_ELIGIBLE cases are
    named with a specific reason, never silently dropped.
    """
    for case in gold_cases:
        if case.dataset_split != DatasetSplit.LOCKED_HOLDOUT:
            raise EvaluationRunError(
                f"GoldCase {case.case_id!r} is not LOCKED_HOLDOUT "
                f"(found {case.dataset_split.value!r}) — cannot be part of an EvaluationRun."
            )
        if not case.locked:
            raise EvaluationRunError(
                f"GoldCase {case.case_id!r} is not locked (see gold_case.lock_gold_case()) "
                f"— cannot be part of an EvaluationRun."
            )
        leak = assess_leakage(case.case_id, case.dataset_split, case.leakage_control)
        if leak.assessment != LeakageAssessment.VALID_FOR_HOLDOUT:
            raise EvaluationRunError(
                f"GoldCase {case.case_id!r} failed leakage assessment "
                f"({leak.assessment.value}): {leak.reason}"
            )

    inexecutable_case_ids = []
    direction_pairs = []  # (expected, actual) for decision_direction_agreement — ELIGIBLE cases only
    safety_serious_pairs = []  # (expected_present: bool, gate_failed: bool)
    agreement_eligibility_by_case = {}  # case_id -> AgreementEligibilityResult, EVERY executed case

    for case in gold_cases:
        try:
            result_df = execute_gold_case_against_engine(case, evidence=case.engine_evidence)
        except GoldCaseNotExecutableError:
            inexecutable_case_ids.append(case.case_id)
            continue

        output = platform_output_for_gold_case(result_df)
        actual_direction = _derive_direction_from_decision_class(output.get("decision_class"))

        # Phase 3 (Prospective Claim-to-Decision Mapping Proposal):
        # eligibility is now assessed and recorded explicitly for
        # EVERY executed case — never a silent skip. Only ELIGIBLE
        # cases (see agreement_eligibility.py for the exact rule —
        # domain currently restricted to INDICATION_EVIDENCE, a
        # mappable AssertionState, and a set expected_decision_direction)
        # contribute to the decision_direction_agreement metric below.
        # This is an intentional behavior change from the module's
        # prior bare "expected is not None and actual is not None"
        # check — a case could previously contribute to this metric
        # without ever having a domain/AssertionState-eligible Ground
        # Truth basis for doing so; that is no longer possible.
        eligibility_result = assess_agreement_eligibility(case)
        agreement_eligibility_by_case[case.case_id] = eligibility_result

        if eligibility_result.eligibility == AgreementEligibility.ELIGIBLE and actual_direction is not None:
            expected_direction = case.expected_output.expected_decision_direction
            direction_pairs.append((expected_direction, actual_direction))

        expected_serious_outcomes = [
            o for o in case.resolved_outcomes if _is_expected_serious_safety_present(o)
        ]
        if expected_serious_outcomes:
            gate_results = output.get("gate_results") or {}
            safety_gate = gate_results.get("safety") or {}
            from data_contracts import GateStatus
            gate_failed = safety_gate.get("status") == GateStatus.FAILED
            safety_serious_pairs.append((True, gate_failed))

    direction_numerator = sum(1 for e, a in direction_pairs if e == a)
    direction_denominator = len(direction_pairs)
    direction_metric = build_proportion_metric(
        "decision_direction_agreement", direction_numerator, direction_denominator,
        detail="Agreement between GoldCase.expected_output (curated summary) and the engine's actual derived direction.",
    )

    # False negative: a ResolvedExpectedOutcome expected a SERIOUS,
    # PRESENT safety assertion, but the engine's safety gate did NOT
    # produce FAILED.
    safety_fn_numerator = sum(1 for expected, gate_failed in safety_serious_pairs if expected and not gate_failed)
    safety_fn_denominator = sum(1 for expected, _ in safety_serious_pairs if expected)
    safety_fn_metric = build_proportion_metric(
        "safety_serious_false_negative_rate", safety_fn_numerator, safety_fn_denominator,
        detail=(
            "Release-blocking metric — computed against GoldCase.resolved_outcomes "
            "(the Reference-Grounded Validation truth), never against a value "
            "supplied to the engine. Must be exactly 0 for any production release profile."
        ),
    )

    return EvaluationRun(
        evaluation_run_id=evaluation_run_id or _new_evaluation_run_id(),
        engine_version=engine_version or _resolve_engine_version(),
        gold_set_version=gold_set_version,
        execution_timestamp=datetime.now(timezone.utc),
        dataset_snapshot_hash=hash_dataset(gold_cases),
        dataset_split_used=DatasetSplit.LOCKED_HOLDOUT.value,
        validation_scope=ValidationScope.PROVIDED_EVIDENCE,
        results=[direction_metric, safety_fn_metric],
        case_count=len(gold_cases),
        inexecutable_case_ids=inexecutable_case_ids,
        agreement_eligibility=agreement_eligibility_by_case,
    )
