# Independent Holdout E2E Validation v1.1 — Structural Blocker Remediation

Total prospective holdout cases: **15**. Structurally executable without Gold evidence injection: **15/15**. Structurally blocked: **0**.

Cases with frozen independent retrieval snapshots and therefore currently scorable: **2**. Pending independent snapshot capture: **13**.

Frozen scored-subset agreement remains **1/2 = 50.0%**; Macro-F1: **0.667**. This score was not changed or re-labelled during blocker remediation.

## What changed

- Candidate discovery no longer requires an exact key in the six-entry legacy map. It uses the existing therapeutic-area registry, global candidate database, and bounded related-concept hypotheses; these are search hypotheses only, never evidence.
- Free-text clinical wording with non-contiguous terms (for example fasting/blood/glucose wording) can resolve to an existing therapeutic family through conservative >=2-token overlap.
- Non-therapeutic identity, preparation, and safety validation cases now use a named-botanical question path. The botanical is explicit question input for those domains, not hidden Gold output. Missing dosage form is no longer fabricated.

## Scored cases (frozen; unchanged)

- refgrounded_001_melissa_officinalis_sleep: reference **GO**, engine **GO**, match=True.
- refgrounded_003_matricaria_chamomilla_sleep: reference **GO WITH CAUTION**, engine **GO**, match=False.

## Remaining validation gap

**No question-schema or candidate-discovery structural blockers remain across the 15 frozen holdout members.**

The remaining **13** unscored cases are waiting only for independently captured retrieval snapshots. They must not be populated from GoldCase reference claims.

## Preserved mismatch

Case 003 remains reference `GO WITH CAUTION` vs engine `GO`. No decision-policy remediation was applied in this phase, so the unseen mismatch remains a valid future development target rather than being tuned away on holdout.

## Next action based on data

Capture independent retrieval snapshots for the remaining 13 frozen holdout members using only their question/context inputs, freeze those snapshots, and only then score them. Do not change the holdout membership or expected labels. In parallel, reproduce the Case 003 scientific-caution failure on development fixtures before any production decision-policy change.
