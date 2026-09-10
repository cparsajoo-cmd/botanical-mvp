# TEST_REPORT.md — Final Pre-Demo Reliability Pass

## Environment correction (important — changes the 9-failure story)

This sandbox was previously missing three optional dependencies:
`streamlit`, `openai`, `supabase`. Installed this pass:
`streamlit==1.63.0`, `openai==3.11.0`, `supabase==2.31.0`.

**With these installed, the pristine ORIGINAL repository ZIP (never
modified) now runs:**

```
3829 passed, 0 failed, 3 xfailed, 0 collection errors
```

versus the previously-reported (under the incompletely-provisioned sandbox)
"3352 passed, 9 failed, 3 xfailed, 60 collection errors." **All 60 previously-
reported collection errors and all 9 previously-reported failures were
category C (environment), not genuine defects, tests, or code issues.**
None required a production fix or a test correction. This is a direct,
verified answer to "review the 9 pre-existing test failures": category C
across the board, confirmed by re-running the untouched original ZIP with
full dependencies rather than asserted from memory.

If your real CI/deployment environment already has these three packages
(likely, since this is a working production platform), this was never a
live issue there — it was specific to this sandbox's setup in earlier
turns.

## Method

Same discipline as the prior pass: a pristine, untouched copy of the
original ZIP is kept alongside the working tree, and every reported
pass/fail delta is the working tree's results **minus** the baseline's own
results on the same command — so any residual failure count reflects only
this pass's changes.

## Full repository suite, this pass's final state

```
pytest -q -p no:cacheprovider --continue-on-collection-errors
```

| | Original ZIP, full deps | This pass's final tree |
|---|---|---|
| Passed | 3829 | 3840 |
| Failed | 0 | 0 |
| xfailed | 3 | 3 |
| Collection errors | 0 | 0 |

**Zero failures, zero newly-introduced collection errors.** The +11
passed count is exactly this pass's new/corrected tests (7 new regression
tests for Defects 2/8/9/Target-Completeness, plus the net effect of
correcting 3 pre-existing tests that encoded now-fixed defects as
intentional behavior — each corrected test still counts once).

## Regression path (what actually happened while fixing Defect 2)

Wiring the Defect 2 fix surfaced real, expected breakage along the way —
reported here rather than hidden, per your instruction not to hide
failures:

1. First full-suite run after the initial Defect 2 wiring: **35 new
   failures.** Root-caused: most were legitimate test fixtures that
   established "direct human clinical" evidence via `Clinical_Rationale`/
   `Scientific_Rationale` text (the module's own standard pattern elsewhere)
   but never populated the separate, narrower `Primary_Outcome`/
   `Source_Evidence_Text` fields my new check was reading — exposing a real,
   independent pre-existing gap in `_row_has_indication_specific_outcome()`
   itself (documented in CHANGE_MANIFEST.md). Fixing that gap directly
   (not just working around it) dropped this to **24 failures.**
2. Of those 24, one was a genuine `NameError` — a bug in my own patch (a
   missing variable initialization on the primary code path), not a test
   issue. Fixed immediately; dropped to **3 failures.**
3. The remaining 3 were tests that explicitly encoded the pre-Defect-2
   contradiction as intentional ("outcome-specific is intentionally
   stricter than direct indication relevance" — a direct quote from one
   test's own comment). Each was corrected individually with a documented
   rationale (see CHANGE_MANIFEST.md §7). Final: **0 failures.**

Defects 8, 9, and Target Definition Completeness were each verified with a
full-suite run immediately after implementation — zero regressions in any
of the three.

## New regression tests added this pass

- `test_candidate_shortlisting.py`:
  `test_zero_verified_outcome_scores_lower_than_verified_direct_human_evidence`
  (Defect 2's exact cahier acceptance test),
  `test_established_class_requires_verified_evidence_not_score_alone`
  (Defect 8),
  `test_incomplete_target_definition_blocks_go_but_not_score_or_shortlist`
  (Target Definition Completeness).
- `test_adjudication_score_authority_wiring.py`:
  `test_final_canonical_direction_follows_verified_evidence_not_ai`,
  `test_final_canonical_direction_falls_back_to_ai_only_when_verified_is_uninformative`
  (Defect 9's exact cahier acceptance scenario — AI says positive/direct,
  verified evidence says otherwise, and the reverse).

All pass in the current tree, individually and as part of the full suite.

## Skipped / not run

None skipped. `xfailed: 3` is unchanged from the original ZIP's own
baseline (pre-existing, expected-fail markers unrelated to this pass).
