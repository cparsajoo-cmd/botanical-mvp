# Scientific phrase-matcher bug fix — before/after summary

## Scope actually touched
- NEW: `scientific_phrase_matcher.py` (shared matching utility)
- NEW: `test_scientific_phrase_matcher.py` (35 tests, written before wiring)
- MODIFIED (matching mechanism only, no other logic touched):
  - `botanical_rd_candidate_engine.py` :: `_evidence_level()`
  - `evidence_hierarchy_classifier.py` :: `_has_term()`
  - `regulatory_barrier_classifier.py` :: `_matches()`
  - `candidate_shortlisting.py` :: `_evidence_points()`
- `DECISION_ENGINE_VERSION` (currently `"1.0.3"`) was **not** changed.
  **Flagging per your versioning policy, not deciding it myself:** the
  plural-form fix changes some real classification outputs (see rows
  2/8/9 below), so this may qualify as a versioned decision-logic
  change under this repo's own policy — please confirm whether it
  should bump.

## Test corpus results (old vs. new)

| # | Text | `_evidence_level` old → new | `_matches` (regulatory) old → new | `_evidence_points` old → new |
|---|------|------------------------------|-------------------------------------|-------------------------------|
| 1 | "A clinical trial demonstrated efficacy." | Clinical / human evidence → *same* | [] → *same* | 26.0 → *same* |
| 2 | "Several clinical trials demonstrated efficacy." | **General literature signal → Clinical / human evidence** | [] → *same* | 26.0 → *same* |
| 3 | "No clinical trials have been conducted." | General literature signal → *same* | [] → *same* | 26.0 → *same* (no negation handling in this function, by design — unchanged) |
| 4 | "Further clinical trials are needed to confirm this." | General literature signal → *same* | [] → *same* | 26.0 → *same* |
| 5 | "This is a preclinical / mechanistic evidence finding." | General literature signal → *same* | [] → *same* | **26.0 → 0.0** |
| 6 | "The product is intended for clinical use." | General literature signal → *same* | [] → *same* | 26.0 → *same* (genuine whole-word "clinical", not a false positive) |
| 7 | "A systematic review of animal models was published." | Clinical / human evidence → *same* | [] → *same* | 30.0 → *same* |
| 8 | "Multiple cohort studies and a WHO monograph support traditional use." | **Regulatory / monograph evidence → Clinical / human evidence** | [] → *same* | 0.0 → *same* |
| 9 | "Controlled substances and novel foods require pre-market approval." | General literature signal → *same* | **[] → ['controlled substance', 'novel food']** | 0.0 → *same* |
| 10 | "The compound underwent in vitro and in vivo testing in rat models." | Preclinical / mechanistic evidence → *same* | [] → *same* | 18.0 → *same* |

**All differences are exactly the ones the fix is scoped to produce:**
- Rows 2, 8: plural forms ("clinical trials", "cohort studies") are now
  correctly detected instead of silently falling through — row 8's
  overall classification changes only because the plural fix lets a
  *stronger* tier (clinical) win a category race it should have won
  all along; "monograph" (singular) was already being detected before
  and after, it's the newly-fixed "cohort studies" that now wins.
- Row 9: plural regulatory-barrier terms now correctly detected.
- Row 5: the "preclinical" substring false positive in
  `candidate_shortlisting.py` is now correctly **not** detected.
- Every other row is byte-for-byte identical old vs. new.

`classify_evidence_hierarchy()` (the 8-tier module) has no "old" column
above because it's purely additive — it didn't exist before this class
of fix and there's nothing to regress against. It benefits from the
same plural fix (e.g. it now also detects "cohort studies").

## Required test-table cases (all 7 phrase families × 4 cases)
Implemented as parametrized tests in `test_scientific_phrase_matcher.py`
for: `clinical_trial`, `systematic_review`, `cohort_study`,
`animal_model`, `monograph`, `controlled_substance`, `novel_food`.
All singular / plural / negated / forward-negated / unrelated-prefix /
unrelated-word cases pass (35/35 tests).

**One deliberate addition beyond a literal copy of the three modules'
original negation-cue lists:** `NEGATION_CUES` in
`scientific_phrase_matcher.py` adds `"further "`, `"additional "`, and
`"more research"` to the pre-existing list, because the required test
table's "Forward-negated" case ("Further clinical trials are needed to
confirm this.") is not covered by the original cue set. This is
additive only — it can only turn a previously-negated-but-undetected
phrase into a correctly-non-matched one, never the reverse — and is
itself covered by `test_forward_negated_does_not_match`.
`candidate_shortlisting.py::_evidence_points()` was **not** switched to
negation-aware matching (it never had negation handling; only its
substring/word-boundary mechanism was fixed) — see the code comment at
that call site.

## Full test suite
`pytest -q` → **2178 passed**, 0 failed, 0 errors (includes the 35 new
tests in `test_scientific_phrase_matcher.py`). Nothing outside the
listed files was touched, so this is a full-suite-clean confirmation,
not a scoped one.

## Explicit constraint compliance
- `ScoringConfig`, `_score_candidate()` weights, `_decision_class()`
  thresholds: unchanged.
- Return type/shape of `_evidence_level()`,
  `classify_evidence_hierarchy()`, `classify_regulatory_barriers()`,
  `_evidence_points()`: unchanged — only their internal matching
  mechanism was replaced.
- `_hard_safety_gate()`, `_extract_flags_negation_aware()`,
  `_extract_hazard_flags_exact()`: not touched.
- `DECISION_ENGINE_VERSION`: not touched — flagged above per policy.
- Nothing outside the four listed files (plus the two new files) was
  modified.
