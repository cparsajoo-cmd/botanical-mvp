# Scientific Validity Architecture Hardening — Engine 1.4.0

## What was wrong
The 1.3.0 body-of-evidence architecture was a major improvement, but it still left an important scientific-validity gap: the engine carried structured fields such as Sample_Size, Comparator, Primary_Outcome, Risk_of_Bias and preparation applicability, while the final body assessor relied mainly on source tier, effect direction, text limitations, source count and freshness.

That allowed missing methodological information to behave too much like a clean assessment.

## What 1.4.0 changes
The final body-of-evidence assessor now receives and evaluates:
- Primary outcome
- Comparator
- Sample size where available
- Risk of bias where available
- Preparation/indication applicability state and detected mismatches
- Existing source tier, direction, limitations, conflict and freshness

Missing domains are explicitly recorded as UNASSESSED. Missing information is never interpreted as “no concern”.

### Scientific safeguards
- High certainty is capped when structured methodological-domain coverage is incomplete.
- Directness mismatches downgrade certainty.
- Explicit high/serious/critical risk-of-bias signals downgrade certainty.
- Small single direct trials are a methodological concern.
- GO remains possible only for supportive HIGH body certainty.
- Lower certainty becomes GO WITH CAUTION rather than unconditional GO.
- Null/negative governing evidence -> INSUFFICIENT EVIDENCE.
- Conflict/newer contradiction -> EXPERT REVIEW REQUIRED.
- Serious safety/regulatory hard stops retain precedence.

## Validation claim is now mechanically gated
`scientific_validity_release_gate.py` prevents the repository from calling an engine version scientifically validated unless ONE finite final benchmark satisfies a predeclared protocol:
- 24 new cases, exactly 4 per six-class decision state
- references frozen before execution
- engine blinded to labels
- no remediation-case reuse
- at least 2 independent human adjudicators
- inter-rater agreement >= 0.70
- accuracy >= 0.80
- macro-F1 >= 0.75
- GO precision >= 0.85
- CAUTION recall >= 0.75
- EXPERT REVIEW recall >= 0.70
- zero serious-safety false negatives
- zero regulatory false negatives

This is intentionally finite: one final 24-case benchmark, not endless case-by-case testing.

## Test status
Dependency-light decision/science/safety regression: 160 passed, 0 failed.
The Supabase-dependent version-tracking test cannot collect in this local environment because the `supabase` package is absent; GitHub CI has the full dependency environment.

Historical exposed holdouts after 1.4.0 remain:
- v3: 60%
- v4: 90%
- v5: 80%
These are regression data only and must NOT be presented as independent v1 accuracy.

## Scientific honesty
This code can make the engine more scientifically conservative and can enforce a credible validation design. It cannot manufacture independent expert agreement. The remaining external-validity step is therefore not another software patch: it is the single frozen 24-case, independently adjudicated benchmark specified in `gold_corpus/scientific_validity/FINAL_HOLDOUT_PROTOCOL_V1.json`.
