# CHANGE_MANIFEST.md — Final Pre-Demo Reliability Pass

This pass started from the ORIGINAL repository ZIP with the previous pass's
valid repairs re-applied (the working tree already contained them; no prior
repair ZIP was actually re-uploaded this turn, confirmed with you and
continued directly on that tree). It completes **Defect 2, Defect 8, Defect 9,
and Target Definition Completeness**, and performs a scoped Defect 10 audit
(see INVESTOR_DEMO_RISK_CHECKLIST.md). No plant or indication name is
hard-coded anywhere in these fixes.

**Preserved unchanged from the prior pass** (verified still present, not
reverted): unreported-direction-≠-MIXED, `INSUFFICIENT_DIRECTION_DATA`,
`TARGET_UNSPECIFIED` vs evidence-`UNKNOWN`, no positive market score for
unassessed search, no positive safety/regulatory score for missing
information, mechanism/compound de-duplication, the explicit `prohibitive`
safety boolean, and the canonical `Primary_Tier_Outcome_Label` ↔
`Evidence_Consistency_Class` mapping.

---

## 1. `candidate_shortlisting.py`

### Defect 2 — direct human relevance now requires verified outcome evidence

**Root cause** (traced across `_indication_relevance_detail_authoritative()`
and its legacy-fallback twin): the "Direct human/clinical" branch (28–35/35
points) only required human-study-design **vocabulary** in a row's text
(`_row_has_candidate_specific_empirical_support()` — checks for
"human"/"clinical"/"randomized"/etc.). It never checked whether the row had
an actual **reported outcome**. Meanwhile `Outcome_Specific_Human_Evidence_Count`
was already built from a separate, stricter function,
`_row_has_indication_specific_outcome()`. The two were never reconciled —
exactly the reported Punica pattern (32.6/35 relevance, 0 verified outcome
evidence).

**Functions changed:**
- `_indication_relevance_detail_authoritative()` and
  `_indication_relevance_detail_legacy_fallback()`: both now track, alongside
  `human_sources`, a stricter `verified_human_sources` count (rows that are
  human-sourced AND clear `_row_has_indication_specific_outcome()`). When
  `human_sources >= 1` but `verified_human_sources == 0`, the mode downgrades
  from `"Direct human/clinical"` to a new `"UNVERIFIED_DIRECT_HUMAN_SIGNAL"`
  state, capped at 24 points (never reaching the 28–35 verified range),
  tier `"Medium relevance"`.
- `_row_has_indication_specific_outcome()`: fixed a genuine pre-existing gap
  — it scanned `Primary_Outcome`/`Source_Outcome_Text`/`Source_Evidence_Text`
  for the indication phrase, but never `Clinical_Rationale`/
  `Scientific_Rationale`, even though `_result_category()` elsewhere in this
  same file already treats those as the record's own reported-outcome
  narrative. Added a branch mirroring the existing `Source_Evidence_Text`
  check (requires a resolved result — `Result_Direction` or a resolvable
  `_result_category()` — AND the indication phrase in the rationale text).
- New plant-status branch for `"UNVERIFIED_DIRECT_HUMAN_SIGNAL"`: always
  routes to `"Exploratory"` (never auto-Shortlisted on this signal alone,
  never Excluded) with explicit provenance text explaining the downgrade.
- `_indication_component_source_ids()`: extended so `UNVERIFIED_DIRECT_HUMAN_SIGNAL`
  rows keep their source-ID provenance visible (previously only `"Direct"`-
  prefixed modes were attributed).
- `_EVIDENCE_ROUTE_BY_MODE`: added an explicit `"direct_human_unverified"`
  route (was falling through to `"unclassified"`).

**Behavior before:** a candidate with zero verified outcome-specific human
evidence could receive near-maximal (28–35/35) "Direct human/clinical"
relevance purely from human-study vocabulary + a strong indication match.

**Behavior after:** the same candidate receives at most 24 points, is labeled
`UNVERIFIED_DIRECT_HUMAN_SIGNAL`, remains fully discoverable, and routes to
Exploratory with a visible reason. A candidate with genuine verified outcome
evidence still reaches "Direct human/clinical" and outranks it.

**A bug in my own first patch, caught by running the suite, not shipped
blind:** the initial edit added the `verified_human_source_ids` tracking
list's *usage* to the primary (`_authoritative`) function but the
corresponding *initialization* only landed in the less-used legacy-fallback
twin — a `NameError` on the production code path. Fixed before delivery.

**Tests:** `test_candidate_shortlisting.py::test_zero_verified_outcome_scores_lower_than_verified_direct_human_evidence`
(the cahier's exact acceptance test — new). Three pre-existing tests that
encoded the old contradiction as intentional design were corrected with
documented rationale (see §7).

### Defect 8 — "Established scientific candidate" requires evidence, not score alone

**Function changed:** `_derive_decision_class_ah()`.

**Before:** `"B — Established scientific candidate"` whenever
`overall_score >= _STRONG_SCORE_THRESHOLD` and status wasn't
Excluded/Exploratory — market novelty, compound count, or mechanism count
could push a weak-evidence candidate over the threshold and manufacture the
label.

**After:** signature extended with `go_call` and `indication_mode` keyword
args. `"B"` requires `go_call == "Go"` (already gates compatible preparation,
explicit reassuring safety, and a predominantly-positive outcome label —
see `_derive_go_call()`) **and** `indication_mode == "Direct human/clinical"`
(verified human outcome evidence specifically, via the Defect 2 fix) **and**
the score threshold. Callers that don't have this context (e.g. the
commercial-only rescore path) default to empty strings, which never satisfy
the condition — missing context withholds "Established", never grants it.

**Both call sites updated** to pass the new keyword args (the plant-scoring
loop passes the just-computed `go_call`/`indication_mode`; the commercial
rescore path passes its own freshly-computed `go_call` and the row's stored
`Indication_Evidence_Mode`).

**Tests:** `test_candidate_shortlisting.py::test_established_class_requires_verified_evidence_not_score_alone`
(new) — covers high-score-but-unverified, high-score-but-not-Go, genuinely
established, and missing-context-defaults-to-withheld.

### Target Definition Completeness — wired into the decision (previously informational only)

**Functions changed:** `_derive_go_call()`, plus the output row dict and the
`authoritative_fields` export tuple.

- `Target_Definition_Completeness` (computed since the prior pass in
  `_scientific_evidence_components()`) was never added to the output row —
  the same "invisible field" pattern this project has hit before
  (RD_Discovery_Lane, Mechanistic_Evidence_Record_IDs). Now on the row and
  in `authoritative_fields`.
- `_derive_go_call()`: new keyword arg `target_definition_completeness`. When
  `"incomplete"`, an otherwise-earned "Go" downgrades to
  `"Investigate — complete target product definition"` — checked *last*,
  after score/safety/dosage/outcome all already justify Go, so a candidate
  never loses Shortlist status or has `Scientific_Evidence_Score` penalized
  for this (unchanged from the Defect-3 fix); it only withholds the final
  "fully transferable" conclusion.
- Both `_derive_go_call()` call sites updated to pass it through.

**Behavior before:** the field existed but nothing read it; an incomplete
target/product definition (e.g. no plant part/dose/route specified) could
still produce an unqualified "Go".

**Behavior after:** same score, same Shortlist eligibility, but "Go" is
withheld until the product definition is complete — never Excluded/No-Go for
this reason alone (least-restrictive, per your instruction).

**Tests:** `test_candidate_shortlisting.py::test_incomplete_target_definition_blocks_go_but_not_score_or_shortlist`
(new).

---

## 2. `step_rd_candidates.py`

### Defect 9 — one canonical final evidence-direction field, documented authority hierarchy

**Function added:** `_final_canonical_evidence_direction(evidence_consistency_class, ai_direction)`.
**Function changed:** `_run_evidence_adjudication()` (new columns wired in);
`_reconcile_final_decision_status()` (docstring only — see below).

**Root cause / finding:** `Indication_Evidence_Direction` (AI-adjudicated,
`evidence_adjudication_engine.py`) and `Evidence_Consistency_Class`
(deterministic, `candidate_shortlisting.py`) were two independent fields with
no documented precedence and no single "canonical" field a reader could
point to. Investigation found `_reconcile_final_decision_status()` already
implements substantial AI-vs-verified reconciliation (many hand-written
gates keyed off `Indication_Evidence_Mode`, which is itself now verified-
evidence-gated after the Defect 2 fix) — so the *effective* behavior already
mostly favored verified evidence, but this was not documented as an explicit
hierarchy and there was no single named field to point to, per your
instruction.

**Fix:** new `_final_canonical_evidence_direction()` with an explicit,
documented 4-level authority hierarchy (source-grounded records → deterministic
`Evidence_Consistency_Class` → AI `Indication_Evidence_Direction` → broad
mechanism/compound plausibility, never itself a direction signal). Verified
evidence (level 2) is used whenever it reflects a resolved classification;
AI (level 3) is used **only** as a labeled fallback when verified evidence
is itself uninformative (`INSUFFICIENT`/`INSUFFICIENT_DIRECTION_DATA`).
Two new columns added to `plant_summary_df` in `_run_evidence_adjudication()`:
`Final_Canonical_Evidence_Direction` and
`Final_Canonical_Evidence_Direction_Source` (`"VERIFIED"`/`"AI_FALLBACK"`/
`"UNKNOWN"`). Neither existing field is deleted, overwritten, or hidden —
both remain independently visible so a reviewer can see when they disagree.

`_reconcile_final_decision_status()` itself was **not** rewritten — its
existing gates were verified (by hand-tracing, then by the new tests below)
to already correctly cap an AI-optimistic-but-unverified candidate at
"GO WITH CAUTION" and never let it reach unqualified "GO". Its docstring
was extended to document why this constitutes the same authority hierarchy
in effect, and to point to the new canonical field, without risking a
rewrite of extensively-tested existing logic this close to the demo.

**Tests:** `test_adjudication_score_authority_wiring.py::test_final_canonical_direction_follows_verified_evidence_not_ai`
(AI says `CONSISTENT_POSITIVE`/`STRONG`, verified says `MIXED` → canonical
field follows `MIXED`, source `VERIFIED`) and
`::test_final_canonical_direction_falls_back_to_ai_only_when_verified_is_uninformative`
(verified is `INSUFFICIENT_DIRECTION_DATA` → canonical field falls back to
the AI read, source `AI_FALLBACK`) — both new, both exercise the real
`_run_evidence_adjudication()` entry point with a mocked `adjudicate_candidate`,
matching this file's existing test pattern.

---

## 3. Other production files in the delivered set

`evidence_consistency.py`, `phase5_scoring_config.py`,
`standard_evidence_builder.py`: **unchanged this pass** — included only
because they were touched in the prior pass and remain part of the current
working tree; re-verified still correct and covered by this pass's
full-suite run.

---

## 4. Defect 10 — fail-gracefully audit (scoped, not a full rewrite)

See INVESTOR_DEMO_RISK_CHECKLIST.md for the full write-up. Summary: audited
(read-only) rather than blindly patched, because the highest-risk item found
(no per-candidate exception isolation in `candidate_shortlisting.py`'s
~700-line plant-scoring loop) would require restructuring that loop to fix
safely, and I judged that too large and risky to attempt correctly with the
remaining time before your demo without real risk of introducing a new,
untested failure mode — which conflicts directly with "no newly introduced
failures are acceptable." No code changes were made for Defect 10 this pass.
Confirmed-safe findings (empty candidate set, missing critical column,
per-connector isolation in Step 2 collection, bounded LLM timeout/retry,
explicit Supabase credential error) and the one verified residual risk are
both documented in the risk checklist rather than claimed fixed.

---

## 5. Review of the 9 previously-reported "pre-existing" test failures

**Finding: all 9 were category C (environment), not defects.** This
sandbox was missing `streamlit`, `openai`, and `supabase`. Installing all
three, **the pristine original ZIP now runs 3829/3829 passed, 0 failed, 3
xfailed, 0 collection errors** (previously reported as 60 collection errors
+ 9 failures under the same, incompletely-provisioned sandbox). None of the
9 were genuine production defects (category A) or stale tests (category B).
See TEST_REPORT.md for the full before/after comparison and package list.

---

## 6. Real Sleep-indication run

No live Supabase/OpenAI access in this sandbox (same constraint as last
pass). See REAL_SLEEP_RUN_DIAGNOSTIC.md for a synthetic-but-real-pipeline
three-candidate comparison (Valeriana/Chamomile/Punica) built directly from
the cahier's own described evidence patterns, run through the actual,
unmodified `build_plant_candidate_shortlist()`.

---

## 7. Test files touched only to correct hard-coded pre-fix expectations

Each was read in full before changing, and none were weakened to pass
incorrect new behavior — every change is documented with the specific
defect it corresponds to, in the test file itself:

- `test_general_evidence_transport_and_ai_alignment_v7.py::test_primary_direct_count_no_longer_depends_on_optional_structured_outcome`
  — previously asserted `"Direct human/clinical"` coexisting with
  `Outcome_Specific_Human_Evidence_Count == 0` as **intentional** design
  ("outcome-specific is intentionally stricter than direct indication
  relevance" — literally the Defect-2 bug, pre-dating its identification).
  Now asserts the corrected `UNVERIFIED_DIRECT_HUMAN_SIGNAL` state.
- `test_candidate_shortlisting.py::test_indication_specific_evidence_is_shortlisted_and_scored`
  — fixture text ("supports wound healing via collagen synthesis") was a
  mechanistic claim, not a reported result; updated to state a genuine
  observed outcome, matching the test's evident intent (verify a truly
  direct-evidence candidate reaches Shortlist).
- `test_phase5_scoring_calibration_addendum.py::test_phase5_lower_tiers_cannot_change_a_primary_tier_go_decision`
  — this fixture's `Clinical_Rationale` never names the indication in its
  own text (only matched via the upstream `Indication_Match_Type` field), so
  it now correctly downgrades to `UNVERIFIED_DIRECT_HUMAN_SIGNAL` /
  Exploratory. Assertions updated to the corrected values; the actual
  invariant under test (lower diagnostic-only tiers cannot change the
  primary-tier decision) is unaffected and still verified.
