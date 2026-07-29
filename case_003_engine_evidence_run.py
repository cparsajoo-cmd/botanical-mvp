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
- POPULATION: ACCEPTABLE_EQUIVALENCE, not EXACT — postnatal women are
  a specific subpopulation, not simply "Adults" in general (real,
  disclosed confound: postpartum physiology/newborn-care sleep
  disruption is a different etiology than general adult sleep
  difficulty). The equivalence judgment here is NOT free-floating: the
  case's own governing source, Kazemi et al. 2024, itself pools this
  same population type (postnatal/postpartum women) into its general
  "healthy or diseased adults" pooled sleep conclusion (see Case 003's
  own module docstring, Applicability Limitation #2). Since the
  Ground-Truth-governing review already treats this population as
  within-scope for a general-adult sleep question, treating this
  specific trial's evidence the same way for Engine Evidence is a
  defensible, source-grounded equivalence — not an EXACT match, and
  not asserted as one.
  PER CASE 003's OWN FROZEN PRINCIPLE ("pass-by-absence is not
  evidence of equivalence"): this ACCEPTABLE_EQUIVALENCE judgment is
  an explicit curator judgment with a stated rationale, not a
  pass-by-absence — it is not the same thing as the reference-side
  applicability check silently passing on an unspecified field.

SEED-DATA COLLISION CHECK (execution_readiness.py, run for real below)
seed_data.SLEEP_TEA_EVIDENCE contains a "Matricaria chamomilla" key
(without an authority suffix) — the SAME latent-collision shape
already disclosed for Melissa officinalis. Checked explicitly below,
not assumed.

WHAT THIS FILE DOES
Attaches EngineEvidenceInput to a COPY of the Case 003 GoldCase
(dataclasses.replace — the frozen builder function itself is never
mutated), runs it through
gold_case_execution.execute_gold_case_with_readiness_gate() — the
single Phase 3C orchestration point — and reports the result. If and
only if the guard returns READY does this file's own call chain reach
the real BotanicalRDCandidateEngine.
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
            equivalence=ScopeEquivalence.ACCEPTABLE_EQUIVALENCE,
            justification=EquivalenceJustification(
                rationale=(
                    "Postnatal women are a specific adult subpopulation, not "
                    "an exact match to this case's general 'Adults' scope. "
                    "Treated as acceptable equivalence, not exact, because "
                    "this case's OWN governing source (Kazemi et al. 2024) "
                    "pools this same population type into its general "
                    "adult-sleep conclusion — see Case 003's own "
                    "Applicability Limitation #2. Not a pass-by-absence."
                ),
                reference_id="CTM_2024_Kazemi_chamomile_sleep_SR",
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

    print("=== Execution Readiness ===")
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
