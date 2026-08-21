# Stage 1 — Evidence Direction Hardening Report

## Status
Completed as a bounded implementation stage. This is engineering/internal-validation hardening, not external scientific validation.

## Baseline diagnosis
A new five-class development benchmark (25 realistic scientific statements; 5 each for positive, negative, null, mixed, unclear) was evaluated before changing production direction logic.

Baseline: 12/25 correct (48.0%). Per-class recall: positive 40%, negative 40%, null 20%, mixed 40%, unclear 100%.

General failure modes included comparative efficacy wording ("more effective than placebo"), explicit efficacy confirmation, non-inferiority, common null-result grammar, harm-direction wording, and mixed time-course/subgroup/endpoint conclusions.

## Production change
`evidence_interpretation.py` was extended only with generic scientific-language patterns. No botanical names, indications, PMIDs, benchmark record IDs, case IDs, scoring weights, gate rules, or final-decision-specific lookup was added.

Added general coverage includes:
- comparative efficacy and confirmed efficacy;
- non-inferiority wording;
- generic significantly lower/higher endpoint comparisons;
- explicit null-result and no-treatment-effect wording;
- ineffective wording and generic serious-adverse-event / toxicity direction;
- mixed conclusions via not-sustained effects, overall-null/subgroup-benefit, and worsening-vs-control clauses.

Structured-source precedence remains unchanged: structured source result > structured LLM result > reported legacy direction > per-record text fallback.

## Development benchmark result after remediation
25/25 correct (100%). Per-class recall: 100% for positive, negative, null, mixed, and unclear. This is **not** an independent validation estimate because this development benchmark was inspected during Stage 1 remediation.

Existing benchmark results remained unchanged:
- legacy human evidence direction benchmark: 11/12 (91.7%);
- calibration v1: 21/24 (87.5%); calibration/development, not independent;
- external validation v2: 7/8 (87.5%); disjoint from calibration v1 according to existing repository governance.

## Versioning
Decision engine version changed from 1.10.0 to 1.10.1 because Evidence Direction can affect downstream scientific interpretation and final decision behavior.

The primary engine changelog still has an unproven historical gap for 1.10.0. Stage 1 does not invent a missing 1.10.0 history; it records only the new 1.10.1 change that is directly evidenced by this patch.

## Tests executed
Focused and relevant regression suite:
- 173 passed, 0 failed.
- Coverage included Stage 1 generalization, five-class benchmark infrastructure, Phase 1 Evidence Direction, structured direction precedence, legacy/calibration/external direction corpora, negative evidence, final-decision authority, eligibility, serious-safety regression, regulatory authorization, scientific reliability invariants, and core reliability regression gate.

Additional checks:
- Python compilation of all Stage 1 Python changes passed.
- Direct import confirmed `DECISION_ENGINE_VERSION == 1.10.1`.

Environment limitation:
- `test_task15_decision_engine_version_tracking.py` could not be collected in this environment because the `supabase` Python package is not installed. The failure was `ModuleNotFoundError: No module named 'supabase'`. Therefore the full version-tracking suite is not claimed as executed here.

## Scientific interpretation
Stage 1 improves general-purpose Evidence Direction language coverage and preserves the existing taxonomy and structured-source precedence. It does not establish clinical validity of the platform, and it does not convert any exposed historical holdout into an independent validation result.
