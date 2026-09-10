# REAL_RUN_SCORING_DIAGNOSTIC.md

## Honest scope of this diagnostic

This sandbox has **no live Supabase connection and no OpenAI API key**, so
the actual 51-candidate Sleep/Relaxation production run described in the
cahier cannot be reproduced here — there is no way to re-query the real
evidence database or re-run the real AI adjudication stage. This document
is **not** that rerun.

Instead, this is a before/after diagnostic run through the real, unmodified
`build_plant_candidate_shortlist()` scoring pipeline (same code path
production uses), against two small synthetic candidates deliberately built
to reproduce the *exact defect patterns* described in the cahier — not
cherry-picked to make the fix look good, but constructed directly from the
cahier's own description of the bugs before writing any fix. Every number
below is a real function output, run against a pristine baseline copy of
the uploaded ZIP vs. the repaired tree, not estimated or invented.

**Recommendation:** re-run the actual Sleep/Relaxation query against the
live Supabase data with these fixes applied to get the authoritative
51-candidate before/after table. This document is a stand-in that
demonstrates the fixes are real and working, not a substitute for that.

## Candidate 1 — "Valeriana-like" (mirrors the cahier's Valerian example)

Constructed: 1 record with a genuinely resolved positive human-RCT
direction, plus 6 records (lower-tier observational studies) whose result
direction was never extracted — same mechanism/compound projected
repeatedly, no market or regulatory search performed.

| Field | Before | After |
|---|---:|---:|
| Overall_Score | 62.8 | 43.5 |
| Indication_Relevance_Score | 32.8 | 32.8 |
| Scientific_Evidence_Score | 7.47 | 7.47 |
| Evidence_Quality_Score | 18.3 | 18.3 |
| Direction_Factor | 0.8 | 0.8 |
| Evidence_Consistency_Class | MOSTLY_POSITIVE | MOSTLY_POSITIVE |
| Plant_Applicability_Factor | 0.6 | 0.6 |
| Compound_Quality_Score | 2.0 | 1.2 |
| Mechanism_Support_Score | 10.0 | 2.0 |
| Safety_Regulatory_Score | 8.0 | 0.0 |
| Novelty_Market_Score | 2.5 | 0.0 |
| Outcome_Consistency | Predominantly positive results | **Mixed/inconsistent results** |
| Final_Decision_Status (Go/Investigate) | Investigate — verify preparation applicability | Investigate — verify preparation applicability |

Notes: the platform's existing tier-precedence logic already keeps the
6 lower-tier (observational) records out of the *primary* evidence tier
used for direction/consistency, so `Evidence_Consistency_Class` itself did
not change here for this particular construction — that part of Defect 1's
concern is already mitigated by tier separation for this data shape.
`Outcome_Consistency`'s label, however, **did** change: the old independent
label heuristic said "Predominantly positive" (1 known-positive record,
unreported-direction records not counted against it) while the canonical
classifier says `MOSTLY_POSITIVE`, i.e. genuinely short of "predominantly."
The corrected label mapping (`MOSTLY_POSITIVE` → "Mixed/inconsistent
results") makes the two fields agree again — this is the concrete fix for
the "internally confusing... must be resolved to one coherent
interpretation" requirement. `Mechanism_Support_Score` dropped from 10→2
because only one unique indication-relevant mechanism component was
present across all 7 duplicate-projected rows (the fix correctly counts 1,
not 7). `Compound_Quality_Score`, `Safety_Regulatory_Score`, and
`Novelty_Market_Score` all correct as described in CHANGE_MANIFEST.md.

## Candidate 2 — "Punica-like" (mirrors the cahier's Punica example)

Constructed: 8 in-vitro mechanistic records, no resolved outcome direction
on any of them, no market/regulatory data — a candidate with real
mechanistic interest but zero outcome-specific human evidence.

| Field | Before | After |
|---|---:|---:|
| Overall_Score | 50.3 | 29.0 |
| Indication_Relevance_Score | 25.8 | 25.8 |
| Scientific_Evidence_Score | 2.03 | **0.0** |
| Evidence_Quality_Score | 14.1 | 14.1 |
| Direction_Factor | 0.4 | **0.0** |
| Evidence_Consistency_Class | MIXED | **INSUFFICIENT_DIRECTION_DATA** |
| Plant_Applicability_Factor | 0.6 | 0.6 |
| Compound_Quality_Score | 2.0 | 1.2 |
| Mechanism_Support_Score | 10.0 | 2.0 |
| Safety_Regulatory_Score | 8.0 | 0.0 |
| Novelty_Market_Score | 2.5 | 0.0 |
| Outcome_Consistency | Results not reported | Results not reported |

Notes: this is the clearest demonstration of the Defect-1 fix. Before: a
candidate with **zero** records of known result direction was classified
`MIXED` — implying a genuine positive/negative disagreement that never
existed — and still received a nonzero `Direction_Factor` (0.4) and
nonzero `Scientific_Evidence_Score` (2.03), i.e. partial efficacy credit
for evidence that establishes no efficacy direction at all. After: the
same input is honestly classified `INSUFFICIENT_DIRECTION_DATA`,
`Direction_Factor` correctly drops to 0.0, and `Scientific_Evidence_Score`
correctly floors at 0.0 — no direction credit is awarded for evidence whose
direction is unknown.

This candidate does **not** demonstrate the other half of the cahier's
Punica concern — `Indication_Relevance_Score` reaching 32.6/35 alongside
`Outcome_Specific_Human_Evidence_Count == 0` (Defect 2, the indication-
relevance-vs-outcome-specific-evidence authority mismatch). That defect was
not fixed in this pass; see CHANGE_MANIFEST.md's "Remaining scientific
limitations."

## Ordering question the cahier asked to be investigated

> "Specifically investigate why a candidate with zero verified
> outcome-specific human evidence can outrank a traditional direct-evidence
> candidate."

Not resolved in this pass. The mechanism responsible is Defect 2 (indication
relevance not requiring verified outcome-specific human evidence for a
near-maximal score) combined with Defect 9 (the AI-adjudicated
`Indication_Evidence_Direction`/`Human_Evidence_Strength` fields being a
separate authority from the scientific-evidence pipeline's own
direction/consistency fields) — neither was investigated or fixed here.
Once those are fixed, the real Sleep run should be re-ranked and the
ordering re-checked against verified evidence, per the cahier's own
instruction not to hard-code the desired ordering.
