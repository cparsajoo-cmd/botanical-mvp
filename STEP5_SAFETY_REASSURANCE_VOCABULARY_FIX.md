# Step 5 Safety_Reassurance vocabulary fix

## Symptom

For Ginkgo biloba, a meta-analysis reports "no important safety concerns
with EGb761 at 240 mg/day", but `Safety_Reassurance` stayed empty
(`NaN`) in the Step 5 output.

## Root cause

`_REASSURANCE_PATTERNS` in `safety_interaction_attribution.py` recognized
only a fixed set of phrasings ("well tolerated", "no serious adverse
events", "no severe adverse events", "no treatment-related adverse events",
"no clinically significant adverse events/effects", "did not cause
toxicity/adverse effects"). "No important safety concerns" is a common
meta-analysis wording that did not match any of them, so the statement fell
through to the adverse-event check, didn't match that either (no adverse
pattern word present), and was dropped entirely — status stayed
`not_assessed` instead of `reassurance_reported`.

This is the same class of fix as the two previous rounds: a vocabulary gap
in the existing pattern lists, not a data-transport or presentation issue.

## Change

- `safety_interaction_attribution.py` — added two patterns to
  `_REASSURANCE_PATTERNS`: `no (?:important|major|significant|serious)
  safety concerns` and a general `no safety concerns` fallback. Both
  `extract_structured_safety_interactions()` and
  `extract_attributed_safety_interactions()` share this same pattern list,
  so the fix applies to structured fields and free-text fallback alike.

## What this does not change

No other pattern lists, connectors, ranking, scoring, UI, Gold Cases, or
database schema were touched.

## Tests

`test_step5_safety_reassurance_vocabulary_fix.py` (new, 4 tests):
- The exact phrase is recognized via the structured-field path.
- A free-text sentence using the phrase is recognized when plant-attributed.
- The general "no safety concerns" fallback is recognized.
- End-to-end: `discover_indication_candidates()` populates
  `Safety_Reassurance` for Ginkgo from a `Safety_Findings` value using this
  wording.

Full suite: 1828 previously-passing tests + 4 new tests = 1832 passed, 0 failed.

## Known remaining gap (not fixed here, flagged for awareness)

The free-text path's plant-anchor logic does not recognize a standardized
extract code name (e.g. "EGb761") as referring to the plant unless the
sentence also uses a generic intervention phrase ("the extract", "this
extract") or an explicit causal-report verb ("was observed", "were
reported", etc.) — see `_has_plant_anchor()` /
`_INTERVENTION_REFERENCES`. The structured-field path (the primary path for
most evidence) is unaffected by this. If reassurance/adverse statements tied
only to a compound code name and not the botanical name in the same sentence
turn out to be common in the free-text fallback, that would need its own
targeted, approved fix — flagging it now rather than folding it in
unreviewed.
