"""
Phase 4 — Engine Evidence Validation, Case 003 (Matricaria chamomilla).

WHY THIS IS A SEPARATE FILE, NOT AN EDIT TO CASE 003's OWN FILE
gold_case_reference_grounded_003_matricaria_chamomilla.py is frozen —
its own docstring states it deliberately does not construct
EngineEvidenceInput, run the engine, or lock the case. Leakage Rule
9.1 requires this to be a separate, later, independently-decided step;
keeping it in its own file also means Case 003's Ground Truth record
is never touched by an execution-time decision.

LEAKAGE-RULE ORDERING (Protocol §9.1) — DOCUMENTED HERE, IN ORDER
1. Ground Truth (ReferenceClaim, resolved_outcomes) was extracted and
   frozen in gold_case_reference_grounded_003_matricaria_chamomilla.py
   BEFORE this file existed.
2. Independent evidence source (Khalid et al. 2025 — see below) was
   located and the EngineEvidenceInput below was drafted AFTER that
   freeze, without editing or re-deriving anything from the frozen
   claim.
3. Only after both of the above does this file call the engine.

INDEPENDENT EVIDENCE SOURCE (THIRD EXECUTION) — Khalid et al. (2025)
"Comparative effect of Chamomile flower (Matricaria chamomilla L.) and
Passion flower (Passiflora incarnata L.) powder tea in patients
suffering from primary insomnia." CyTA - Journal of Food. DOI
10.1080/19476337.2025.2504527. Published online 16 May 2025.
Chosen to REPLACE Chang & Chen (2016) as this case's Engine Evidence
after a fresh, criteria-driven search (population closer to
"Adults" — no postpartum/institutional confound — while remaining a
real oral tea preparation). Published AFTER Kazemi et al. 2024's
literature-search cutoff (August 2023), so it could not have been one
of that review's own pooled studies — a real, verifiable form of
source independence, not merely asserted.
Evidence built ONLY from the study's own reported design/population/
intervention/duration/results — explicitly excluding its Discussion
section's references to earlier literature and its liver-function/
melatonin sub-findings, which are not needed for the sleep evidence
input and were never verified against this case's own Ground Truth or
any other source.

DIMENSION-EQUIVALENCE JUDGMENTS (curator-supplied, explicit — per
execution_readiness.py's design: the guard never infers these itself)
- ROUTE: EXACT. Oral in both.
- PREPARATION: ACCEPTABLE_EQUIVALENCE, not EXACT. The study used 1 g
  chamomile flower powder steeped directly in 250 ml boiling water for
  10 minutes and consumed as tea — the same plant material, aqueous
  solvent, and oral tea form as PreparationSpec(dosage_form="Infusion",
  solvent="water"). Held short of EXACT because the paper describes it
  as "powder tea," and nothing in its Methods confirms the solids were
  filtered out before consumption the way a classic strained infusion
  is — a real, disclosed uncertainty, not treated as disqualifying.
- POPULATION: ACCEPTABLE_EQUIVALENCE, not EXACT — reassessed using
  ONLY this study's own population and this case's ValidationUnit,
  per the standing rule (Ground-Truth-derived rationale is not
  permitted for scope-equivalence judgments, per the prior methodological
  decision on this case). The trial's 90 participants, aged 25-45,
  were selected on the basis of a sleep-quality/primary-insomnia
  criterion — an adult population defined by the sleep complaint
  itself, with no unrelated physiological or institutional confound
  (unlike Chang & Chen's postpartum women). Still not EXACT, since
  "Adults" in the ValidationUnit is not itself restricted to a
  clinical insomnia diagnosis — but the absence of a confounding
  factor, plus the population being defined by essentially the same
  concern this case's indication targets, supports ACCEPTABLE_
  EQUIVALENCE with this rationale alone.

SEED-DATA COLLISION CHECK (execution_readiness.py, run for real below)
seed_data.SLEEP_TEA_EVIDENCE contains a "Matricaria chamomilla" key
(without an authority suffix) — the SAME latent-collision shape
already disclosed for Melissa officinalis. Checked explicitly below,
not assumed.

EVIDENCE-CHANNEL FIX (already in place, unaffected by this change)
gold_case_execution.execute_gold_case_with_readiness_gate() computes
one effective_evidence value from GoldCase.engine_evidence, used
identically by both the readiness guard and the engine call — see
gold_case_execution.py's own docstring for the fix history.

WHAT THIS FILE DOES
Attaches EngineEvidenceInput to a COPY of the Case 003 GoldCase
(dataclasses.replace — the frozen builder function itself is never
mutated), runs it through
gold_case_execution.execute_gold_case_with_readiness_gate() — the
single Phase 3C orchestration point — and reports the result. If and
only if the guard returns READY does this file's own call chain reach
the real BotanicalRDCandidateEngine.

THIS IS THE THIRD, SEPARATE EXECUTION — NEITHER PRIOR RESULT IS
OVERWRITTEN OR REINTERPRETED
1. Original execution: READY, engine ran, minimum_evidence
   NOT_EVALUABLE — caused by the evidence-channel bug (since fixed).
2. Second execution (rerun after the channel fix): DEFER —
   population reassessed as UNKNOWN using Chang & Chen (2016) as the
   candidate evidence, with no protocol-defined basis to call it
   equivalent.
3. THIS execution: a different independent evidence source (Khalid
   et al. 2025), reassessed dimensions, reported fully below on its
   own terms.
Both prior results remain documented in the project's conversation
record exactly as they were produced.
"""

from __future__ import annotations

from dataclasses import replace

from engine_evidence_input import EngineEvidenceInput, EngineEvidenceOrigin
from execution_readiness import (
    DimensionAssessment, EquivalenceJustification, ExecutionReadiness,
    ScopeDimension, ScopeEquivalence,
)
from gold_case_execution import execute_gold_case_with_readiness_gate, platform_output_for_gold_case
from gold_case_reference_grounded_003_matricaria_chamomilla import (
    build_gold_case_refgrounded_003_matricaria_chamomilla_sleep,
)


def _independent_engine_evidence() -> EngineEvidenceInput:
    """Khalid et al. 2025 — see module docstring. Built ONLY from the
    study's own Methods/Results (design, population, intervention,
    comparator, duration, directly reported sleep outcomes) — no
    Discussion-section literature references, no mechanistic claims
    attributed to earlier work, no liver-function/melatonin content
    (not needed for sleep evidence), and no restatement of the frozen
    Ground Truth or of Kazemi et al. 2024."""
    return EngineEvidenceInput(
        scientific_name="Matricaria chamomilla L.",
        target_indication="Sleep quality",
        notes=(
            "A randomized controlled trial in 90 participants aged 25-45 "
            "with primary insomnia (selected using the Pittsburgh Sleep "
            "Quality Index), divided into three groups: control, chamomile "
            "flower powder tea (1 g powder steeped in 250 ml boiling water "
            "for 10 minutes, consumed daily), and passionflower powder tea, "
            "for 8 weeks. Chamomile significantly alleviated insomnia "
            "symptoms compared with passionflower, and reduced daytime "
            "dysfunction and salivary cortisol levels, indicating stress "
            "reduction; passionflower showed no significant change in "
            "cortisol."
        ),
        compound_activity_targets=(),  # no independent structured compound-activity data available
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
                    "1 g chamomile flower powder steeped in 250 ml boiling "
                    "water for 10 minutes, consumed as tea — same plant "
                    "material, aqueous solvent, and oral tea form as "
                    "Infusion/water. Not EXACT because the study describes "
                    "it as 'powder tea' and its Methods do not confirm "
                    "solids were filtered out before consumption, unlike a "
                    "classic strained infusion — a disclosed uncertainty, "
                    "not a disqualifying one."
                ),
            ),
        ),
        DimensionAssessment(
            dimension=ScopeDimension.POPULATION,
            equivalence=ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(
                rationale=(
                    "Reassessed using only this case's ValidationUnit "
                    "population ('Adults') and the trial's own reported "
                    "population — no reference to Ground Truth or to "
                    "Kazemi et al. 2024. 90 adults aged 25-45 selected on a "
                    "sleep-quality/primary-insomnia criterion — an adult "
                    "population defined by the same concern this case's "
                    "indication targets, with no unrelated physiological or "
                    "institutional confound (contrast with Chang & Chen "
                    "2016's postpartum women, previously assessed UNKNOWN "
                    "for that reason). Not EXACT, since 'Adults' in the "
                    "ValidationUnit is not itself restricted to a clinical "
                    "insomnia diagnosis."
                ),
            ),
        ),
    )


def run_case_003_through_readiness_gate():
    base_case = build_gold_case_refgrounded_003_matricaria_chamomilla_sleep()

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


if __name__ == "__main__":
    case, readiness, result_df = run_case_003_through_readiness_gate()

    print("=== THIRD EXECUTION — Khalid et al. 2025 as independent Engine Evidence ===")
    print("(original READY/NOT_EVALUABLE run, and the second UNKNOWN/DEFER run, both preserved separately)")

    print("\n=== 1. Execution Readiness ===")
    print("case_id:", readiness.case_id)
    print("decision:", readiness.decision.value)
    print("reasons:", [r.value for r in readiness.reasons])

    print("\n=== 2. Effective-evidence confirmation ===")
    print("case.engine_evidence set:", bool(case.engine_evidence))
    print("case.engine_evidence[0].notes (first 80 chars):", case.engine_evidence[0].notes[:80] if case.engine_evidence else None)
    print("NO_ENGINE_EVIDENCE in reasons (should be False if evidence reached the guard):",
          any("No engine evidence" in r.value for r in readiness.reasons))

    print("\n=== Ground Truth (frozen, for comparison) ===")
    gt = case.resolved_outcomes[0]
    print("assertion_state:", gt.assertion_state)
    print("selected_reference_id:", gt.selected_reference_id)

    if readiness.decision == ExecutionReadiness.READY:
        row = result_df.iloc[0]

        print("\n=== 3. Every gate result ===")
        for gate_name, gate in row["Gate_Results"].items():
            print(f"- {gate_name}: status={gate['status'].value!r}, reason={gate['reason']!r}, evidence={gate.get('evidence')!r}")

        print("\n=== 4. Platform decision fields ===")
        output = platform_output_for_gold_case(result_df)
        for key, value in output.items():
            print(f"{key}: {value}")

        print("\n=== 5/6. Comparison with Ground Truth (reported, not auto-classified) ===")
        print(f"Ground Truth: assertion_state={gt.assertion_state} (a claim-level, mixed/qualified finding)")
        print(f"Engine: decision_class={output.get('decision_class')!r}, decision_class_ah={output.get('decision_class_ah')!r}")
        print("NOTE: these are two different taxonomies (claim-level AssertionState vs. "
              "candidate-level Decision_Class) — see accompanying report for why a forced "
              "binary agree/disagree label is not applied here.")
    else:
        print("\n=== Engine NOT executed (guard did not return READY) ===")
        print("result_df is None:", result_df is None)
