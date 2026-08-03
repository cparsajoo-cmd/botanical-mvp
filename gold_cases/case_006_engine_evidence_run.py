"""
Phase 7 — Engine Evidence, Execution, and Locking, Case 006
(Hypericum perforatum / SAFETY contraindication).

WHY THIS IS A SEPARATE FILE, NOT AN EDIT TO CASE 006's OWN FILE
gold_case_reference_grounded_006_hypericum_perforatum_safety_
interaction.py is frozen — its own docstring states it deliberately
does not construct EngineEvidenceInput, run the engine, or lock the
case. Leakage Rule 9.1 requires this to be a separate, later,
independently-decided step; keeping it in its own file also means Case
006's Ground Truth record is never touched by an execution-time
decision. This mirrors case_003_engine_evidence_run.py's own,
already-established convention exactly.

LEAKAGE-RULE ORDERING (Protocol §9.1) — DOCUMENTED HERE, IN ORDER
1. Ground Truth (ReferenceClaim, resolved_outcomes — domain=SAFETY,
   assertion_type=CONTRAINDICATION, assertion_state=PRESENT,
   severity=SERIOUS via severity_assignment_policy.py,
   resolution_status=SELECTED) was extracted, corrected, and frozen in
   gold_case_reference_grounded_006_hypericum_perforatum_safety_
   interaction.py across several supervised revisions, BEFORE this
   file existed.
2. The EngineEvidenceInput below was drafted AFTER that freeze, from
   independent general pharmacology knowledge about Hypericum
   perforatum's known mechanism of drug interaction (hyperforin-driven
   induction of hepatic CYP450 enzymes and P-glycoprotein) — worded
   independently, not copied from the frozen ReferenceClaim's verbatim
   EMA text, and containing neither the governing reference's
   reference_id nor any distinguishing digit run from EMA/HMPC/7695/
   2021 (checked mechanically below by execution_readiness.py's own
   ENGINE_EVIDENCE_SOURCE_OVERLAP heuristic, not merely asserted here).
3. Only after both of the above does this file call the engine, via
   the readiness gate (Phase 3C orchestration point).

WHAT THIS FILE DOES
Attaches EngineEvidenceInput to a COPY of the Case 006 GoldCase
(dataclasses.replace — the frozen builder function itself is never
mutated), runs it through
gold_case_execution.execute_gold_case_with_readiness_gate(), verifies
agreement at the "safety" gate specifically (per
evaluation_run.py's own _is_expected_serious_safety_present() /
safety_serious_false_negative_rate definition — a SERIOUS+PRESENT
SAFETY outcome agrees iff Gate_Results["safety"]["status"] ==
GateStatus.FAILED), and locks the resulting case if and only if every
mechanical validation step completed successfully.

WHAT "VALIDATION STEP SUCCEEDS" MEANS FOR LOCKING (stated explicitly,
because Protocol §10 is explicit that engine/reference AGREEMENT is
NOT itself a success criterion)
"Success," for locking purposes, means the validation apparatus itself
worked correctly and produced a real, evaluable answer:
  - execution_readiness returned READY (Ground Truth complete, no
    source overlap, all three scope dimensions assessed, no seed-data
    collision),
  - the engine executed without error, and
  - the "safety" gate produced an affirmative finding (PASSED or
    FAILED — a real answer), not NOT_EVALUABLE (which would mean the
    gate genuinely could not be assessed from the evidence given).
Whether the gate's affirmative finding AGREES with Ground Truth
(FAILED, the expected direction for a SERIOUS+PRESENT contraindication)
or DISAGREES (PASSED — a genuine false negative) is reported honestly
either way and does NOT by itself block locking — per Protocol §10/§11,
disagreement is a valid, informative, lockable result; only a
mechanical execution failure blocks locking here.

DIMENSION-EQUIVALENCE JUDGMENTS (curator-supplied, explicit — per
execution_readiness.py's design: the guard never infers these itself)
- ROUTE: EXACT. Oral in both — general pharmacokinetic knowledge about
  hepatic/systemic enzyme induction from an orally consumed herbal
  extract applies directly to oral use, the case's own route.
- PREPARATION: ACCEPTABLE_EQUIVALENCE, not EXACT. The induction
  mechanism is attributed in the general pharmacology literature to
  hyperforin content broadly across Hypericum perforatum extracts,
  not to one single DER/solvent combination — held short of EXACT
  because this note does not itself specify DER 3-7:1/methanol 80%
  V/V precisely, only the taxon and its known constituent-driven
  mechanism.
- POPULATION: ACCEPTABLE_EQUIVALENCE, not EXACT. General pharmacology
  knowledge of this mechanism is not population-restricted (it is a
  hepatic-enzyme-level pharmacokinetic effect expected in any adult
  taking concomitant medication) — reasonably covers "Adults and
  elderly" without being a population-specific clinical finding.
"""

from __future__ import annotations

from dataclasses import replace

from data_contracts import GateStatus
from dataset_split import LeakageAssessment, assess_leakage
from engine_evidence_input import EngineEvidenceInput, EngineEvidenceOrigin
from execution_readiness import (
    DimensionAssessment, EquivalenceJustification, ExecutionReadiness,
    ScopeDimension, ScopeEquivalence,
)
from gold_case import GoldCaseNotReadyError, is_lockable, lock_gold_case
from gold_case_execution import execute_gold_case_with_readiness_gate, platform_output_for_gold_case
from gold_case_reference_grounded_006_hypericum_perforatum_safety_interaction import (
    build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction,
)


def _independent_engine_evidence() -> EngineEvidenceInput:
    """Drafted from general pharmacology knowledge about Hypericum
    perforatum's mechanism of drug interaction, independently worded —
    see module docstring's leakage-rule-ordering section. target_
    indication is left None: this case is indication-independent (see
    Case 006's own module docstring), and target_indication is now
    Optional per the architecture fix in gold_case_execution.py /
    engine_evidence_input.py — no placeholder value is substituted."""
    return EngineEvidenceInput(
        scientific_name="Hypericum perforatum L.",
        target_indication=None,
        notes=(
            "Hyperforin, a major phloroglucinol constituent of Hypericum "
            "perforatum extracts, is a well-characterized inducer of "
            "hepatic cytochrome P450 metabolic enzymes and of the "
            "P-glycoprotein drug efflux transporter, acting via activation "
            "of the pregnane X receptor (PXR). This induction increases "
            "the clearance of many co-administered medicines, lowering "
            "their plasma concentrations and reducing their therapeutic "
            "effect while the extract is taken."
        ),
        compound_activity_targets=(
            "Cytochrome P450 enzyme induction",
            "P-glycoprotein transporter induction",
        ),
    )


def _dimension_assessments() -> tuple:
    return (
        DimensionAssessment(
            dimension=ScopeDimension.ROUTE,
            equivalence=ScopeEquivalence.EXACT,
            detail="Oral in both.",
        ),
        DimensionAssessment(
            dimension=ScopeDimension.PREPARATION,
            equivalence=ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(
                rationale=(
                    "The hepatic-enzyme/P-glycoprotein induction mechanism "
                    "is attributed in general pharmacology literature to "
                    "hyperforin content across Hypericum perforatum "
                    "extracts broadly, not to one specific DER/solvent "
                    "combination. Not EXACT because this evidence does not "
                    "itself specify DER 3-7:1/methanol 80% V/V."
                ),
            ),
        ),
        DimensionAssessment(
            dimension=ScopeDimension.POPULATION,
            equivalence=ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(
                rationale=(
                    "The induction mechanism is a hepatic pharmacokinetic "
                    "effect expected in any adult taking concomitant "
                    "medication, not a population-restricted clinical "
                    "finding — reasonably covers 'Adults and elderly' "
                    "without being population-specific evidence."
                ),
            ),
        ),
    )


def run_case_006_through_readiness_gate():
    base_case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()

    # dataclasses.replace — the frozen Ground Truth builder function
    # and its return value are never mutated in place.
    case_with_evidence = replace(
        base_case,
        engine_evidence=[_independent_engine_evidence()],
        engine_evidence_origin=EngineEvidenceOrigin.CURATOR_SUPPLIED,
    )

    readiness, result_df = execute_gold_case_with_readiness_gate(
        case_with_evidence,
        dimension_assessments=_dimension_assessments(),
    )

    return case_with_evidence, readiness, result_df


def verify_safety_gate_agreement(case_with_evidence, result_df) -> dict:
    """Verifies agreement at the 'safety' gate specifically, per
    evaluation_run.py's own definition (_is_expected_serious_safety_
    present() / safety_serious_false_negative_rate): a SERIOUS+PRESENT
    SAFETY resolved outcome agrees with the engine iff
    Gate_Results['safety']['status'] == GateStatus.FAILED. Returns a
    plain dict report; never raises on disagreement (disagreement is a
    valid, informative result — see module docstring)."""
    from reference_precedence import ResolutionStatus
    from assertion_vocabulary import AssertionState, SeverityLevel
    from applicability_check import ReferenceDomain

    expected_serious_outcomes = [
        o for o in case_with_evidence.resolved_outcomes
        if (
            o.domain == ReferenceDomain.SAFETY
            and o.resolution_status == ResolutionStatus.SELECTED
            and o.severity == SeverityLevel.SERIOUS
            and o.assertion_state == AssertionState.PRESENT
        )
    ]

    output = platform_output_for_gold_case(result_df)
    gate_results = output.get("gate_results") or {}
    safety_gate = gate_results.get("safety") or {}
    safety_status = safety_gate.get("status")

    return {
        "expected_serious_present_outcome_exists": bool(expected_serious_outcomes),
        "safety_gate_status": safety_status,
        "safety_gate_reason": safety_gate.get("reason"),
        "gate_evaluable": safety_status in (GateStatus.PASSED, GateStatus.FAILED),
        "agrees_with_ground_truth": bool(expected_serious_outcomes) and safety_status == GateStatus.FAILED,
        "all_gate_results": gate_results,
    }


def lock_if_valid(case_with_evidence, readiness, result_df, gate_report):
    """Locks the case iff every mechanical validation step succeeded —
    see module docstring's 'WHAT VALIDATION STEP SUCCEEDS MEANS FOR
    LOCKING'. Returns (locked_case_or_none, validation_notes: list).
    Never locks on a BLOCK/DEFER readiness decision, a failed leakage
    assessment, a NOT_EVALUABLE safety gate, or an is_lockable()
    failure — but does NOT require gate agreement (disagreement alone
    never blocks a lock)."""
    notes = []

    if readiness.decision != ExecutionReadiness.READY:
        notes.append(f"NOT LOCKED: readiness={readiness.decision.value!r}, reasons={[r.value for r in readiness.reasons]}")
        return None, notes

    if result_df is None or result_df.empty:
        notes.append("NOT LOCKED: engine produced no result row for this case.")
        return None, notes

    if not gate_report["gate_evaluable"]:
        notes.append(
            f"NOT LOCKED: safety gate status is {gate_report['safety_gate_status']!r}, "
            f"not an affirmative PASSED/FAILED finding."
        )
        return None, notes

    leakage = assess_leakage(
        case_with_evidence.case_id, case_with_evidence.dataset_split, case_with_evidence.leakage_control,
    )
    if leakage.assessment != LeakageAssessment.VALID_FOR_HOLDOUT:
        notes.append(f"NOT LOCKED: leakage assessment={leakage.assessment.value!r}: {leakage.reason}")
        return None, notes

    lockable, reasons = is_lockable(case_with_evidence)
    if not lockable:
        notes.append(f"NOT LOCKED: is_lockable()=False, reasons={reasons}")
        return None, notes

    try:
        locked_case = lock_gold_case(case_with_evidence)
    except GoldCaseNotReadyError as exc:
        notes.append(f"NOT LOCKED: lock_gold_case() raised: {exc}")
        return None, notes

    notes.append(
        f"LOCKED: dataset_snapshot_hash={locked_case.dataset_snapshot_hash!r}. "
        f"Gate agreement with Ground Truth: {gate_report['agrees_with_ground_truth']} "
        f"(status={gate_report['safety_gate_status']!r}) — agreement itself is not a "
        f"locking precondition; recorded here for transparency only."
    )
    return locked_case, notes


if __name__ == "__main__":
    case, readiness, result_df = run_case_006_through_readiness_gate()

    print("=== 1. Execution Readiness ===")
    print("case_id:", readiness.case_id)
    print("decision:", readiness.decision.value)
    print("reasons:", [r.value for r in readiness.reasons])

    print("\n=== Ground Truth (frozen, for comparison) ===")
    gt = case.resolved_outcomes[0]
    print("domain:", gt.domain.value)
    print("assertion_type:", gt.assertion_type.value)
    print("assertion_state:", gt.assertion_state)
    print("severity:", gt.severity)
    print("resolution_status:", gt.resolution_status.value)
    print("selected_reference_id:", gt.selected_reference_id)

    if readiness.decision == ExecutionReadiness.READY:
        print("\n=== 2. Every gate result ===")
        row = result_df.iloc[0]
        for gate_name, gate in row["Gate_Results"].items():
            print(f"- {gate_name}: status={gate['status'].value!r}, reason={gate['reason']!r}, evidence={gate.get('evidence')!r}")

        print("\n=== 3. Platform decision fields ===")
        output = platform_output_for_gold_case(result_df)
        for key, value in output.items():
            if key != "gate_results":
                print(f"{key}: {value}")

        print("\n=== 4. SAFETY gate agreement verification ===")
        gate_report = verify_safety_gate_agreement(case, result_df)
        for key, value in gate_report.items():
            if key != "all_gate_results":
                print(f"{key}: {value}")

        print("\n=== 5. Locking decision ===")
        locked_case, notes = lock_if_valid(case, readiness, result_df, gate_report)
        for note in notes:
            print(note)
        print("final locked state:", locked_case.locked if locked_case else False)
    else:
        print("\n=== Engine NOT executed (guard did not return READY) ===")
        print("result_df is None:", result_df is None)
