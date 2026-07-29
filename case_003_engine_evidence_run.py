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
2. Independent evidence source (Chang & Chen 2016) was located and
   the EngineEvidenceInput below was drafted AFTER that freeze,
   without editing or re-deriving anything from the frozen claim.
3. Only after both of the above does this file call the engine.

INDEPENDENT EVIDENCE SOURCE — Chang & Chen (2016)
"Effects of an intervention with drinking chamomile tea on sleep
quality and depression in sleep disturbed postnatal women: a
randomized controlled trial." Journal of Advanced Nursing 72(2):
306-315. DOI 10.1111/jan.12836.
A DIFFERENT, independent primary trial — not the Kazemi et al. 2024
systematic review that governs this case's Ground Truth (source
independence: this is one of literature's many chamomile-sleep RCTs,
cited independently here, not derived from or quoting the governing
review's own conclusion).

DIMENSION-EQUIVALENCE JUDGMENTS (curator-supplied, explicit — per
execution_readiness.py's design: the guard never infers these itself)
- PREPARATION: EXACT. Chang & Chen used a teabag of 2 g dried
  chamomile flowers steeped in hot water — a water-based herbal
  infusion, matching PreparationSpec(dosage_form="Infusion",
  solvent="water") directly, not merely by curator judgment.
- ROUTE: EXACT. Oral in both.
- POPULATION: UNKNOWN — REASSESSED, Ground-Truth-based rationale
  REMOVED. An earlier version of this file justified
  ACCEPTABLE_EQUIVALENCE by citing that Case 003's own governing
  systematic review (Kazemi et al. 2024) pools this same population
  type into its pooled conclusion. That reasoning has been withdrawn:
  citing the Ground-Truth-governing source to shape an Engine-Evidence
  scope-equivalence judgment risks shaping Engine Evidence design
  around knowledge drawn from Ground Truth, which is exactly the
  category of influence Leakage Rule 9.1 exists to prevent — even
  though it does not inject the Ground Truth's actual CONCLUSION into
  the evidence text itself.
  Reassessed using ONLY: (a) this case's ValidationUnit.population =
  "Adults"; (b) Chang & Chen's actual trial population = postnatal
  women with poor sleep; (c) the protocol/guard's own defined
  ScopeEquivalence categories (EXACT / ACCEPTABLE_EQUIVALENCE /
  MISMATCH / UNKNOWN). Neither the frozen VALIDATION_PROTOCOL.md nor
  execution_readiness.py define a concrete threshold for how much
  population-specificity does or does not disqualify equivalence —
  and postpartum physiology / newborn-care-driven sleep disruption is
  a real, plausible confound relative to general adult sleep
  difficulty, not a trivial demographic technicality. Absent a
  protocol-defined basis to confidently call this either an acceptable
  equivalence or a confirmed mismatch, UNKNOWN is the honest
  classification — not stretched to ACCEPTABLE_EQUIVALENCE to reach
  READY. See _dimension_assessments() below: no EquivalenceJustification
  is attached, and none is required for UNKNOWN.

SEED-DATA COLLISION CHECK (execution_readiness.py, run for real below)
seed_data.SLEEP_TEA_EVIDENCE contains a "Matricaria chamomilla" key
(without an authority suffix) — the SAME latent-collision shape
already disclosed for Melissa officinalis. Checked explicitly below,
not assumed.

EVIDENCE-CHANNEL FIX (applies to this rerun)
gold_case_execution.execute_gold_case_with_readiness_gate() previously
read GoldCase.engine_evidence and its own `evidence=` parameter as two
independent, unsynchronized channels — the ORIGINAL run of this file
set engine_evidence on the case copy but never passed evidence=
explicitly, so the guard saw evidence (READY) while the engine received
none (NOT_EVALUABLE minimum_evidence gate). That has been fixed at the
wrapper level (_resolve_effective_evidence() in gold_case_execution.py);
this file's call below is unchanged (it only ever set
GoldCase.engine_evidence), and now works correctly as a side effect of
the wrapper fix, not because this file itself changed how it calls in.

WHAT THIS FILE DOES
Attaches EngineEvidenceInput to a COPY of the Case 003 GoldCase
(dataclasses.replace — the frozen builder function itself is never
mutated), runs it through
gold_case_execution.execute_gold_case_with_readiness_gate() — the
single Phase 3C orchestration point — and reports the result. If and
only if the guard returns READY does this file's own call chain reach
the real BotanicalRDCandidateEngine.

THIS IS A RERUN, NOT A REPLACEMENT OF THE ORIGINAL RESULT
The original execution (READY, engine ran, minimum_evidence
NOT_EVALUABLE due to the evidence-channel bug) is preserved as a
documented finding in the project's conversation record and is not
overwritten or reinterpreted here. This file, run again after both the
wrapper fix and the population reassessment, produces a NEW, separate
result reported on its own terms.
"""

from __future__ import annotations

from dataclasses import replace

from engine_evidence_input import EngineEvidenceInput, EngineEvidenceOrigin
from execution_readiness import (
    DimensionAssessment, ExecutionReadiness,
    ScopeDimension, ScopeEquivalence,
)
from gold_case_execution import execute_gold_case_with_readiness_gate, platform_output_for_gold_case
from gold_case_reference_grounded_003_matricaria_chamomilla import (
    build_gold_case_refgrounded_003_matricaria_chamomilla_sleep,
)


def _independent_engine_evidence() -> EngineEvidenceInput:
    """Chang & Chen 2016 — see module docstring. Plain factual
    description in the curator's own words; no EMA/regulatory
    vocabulary (not applicable to this source anyway), no restatement
    of the Kazemi 2024 systematic review's own CONDITIONAL/mixed
    conclusion."""
    return EngineEvidenceInput(
        scientific_name="Matricaria chamomilla L.",
        target_indication="Sleep quality",
        notes=(
            "A randomized controlled trial (pretest-post-test design) in "
            "80 postnatal women with poor sleep quality, assigned to drink "
            "one cup of chamomile tea daily (a teabag of 2 g dried "
            "chamomile flowers steeped in hot water) for two weeks, or "
            "usual postpartum care. The tea group showed significantly "
            "lower physical-symptom-related sleep inefficiency and "
            "depression scores than the control group at the two-week "
            "endpoint; the difference was not sustained at four-week "
            "follow-up."
        ),
        compound_activity_targets=(),  # no independent structured compound-activity data available
    )


def _dimension_assessments() -> tuple:
    return (
        DimensionAssessment(
            dimension=ScopeDimension.PREPARATION,
            equivalence=ScopeEquivalence.EXACT,
            detail="Water-based herbal tea infusion, matches Infusion/water directly.",
        ),
        DimensionAssessment(
            dimension=ScopeDimension.ROUTE,
            equivalence=ScopeEquivalence.EXACT,
            detail="Oral in both.",
        ),
        DimensionAssessment(
            dimension=ScopeDimension.POPULATION,
            equivalence=ScopeEquivalence.UNKNOWN,
            detail=(
                "Reassessed independently of Ground Truth (see module "
                "docstring). ValidationUnit population is 'Adults'; the "
                "trial's actual population is postnatal women with poor "
                "sleep — a real, plausible physiological confound "
                "(postpartum state / newborn-care sleep disruption), not "
                "merely a demographic subset. No protocol-defined "
                "threshold exists to confidently classify this as either "
                "acceptable equivalence or a confirmed mismatch, so it is "
                "recorded as UNKNOWN rather than stretched toward READY."
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

    print("=== RERUN — after evidence-channel fix + independent population reassessment ===")
    print("(original run's READY/NOT_EVALUABLE result is preserved separately, not overwritten)")
    print("\n=== Execution Readiness ===")
    print("case_id:", readiness.case_id)
    print("decision:", readiness.decision.value)
    print("reasons:", [r.value for r in readiness.reasons])

    print("\n=== Ground Truth (frozen, for comparison) ===")
    gt = case.resolved_outcomes[0]
    print("assertion_state:", gt.assertion_state)
    print("selected_reference_id:", gt.selected_reference_id)

    if readiness.decision == ExecutionReadiness.READY:
        print("\n=== Engine executed — real output ===")
        output = platform_output_for_gold_case(result_df)
        for key, value in output.items():
            print(f"{key}: {value}")
    else:
        print("\n=== Engine NOT executed (guard did not return READY) ===")
        print("result_df is None:", result_df is None)
