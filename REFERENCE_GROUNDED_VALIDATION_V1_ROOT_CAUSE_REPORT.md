# Reference-Grounded Validation v1 — Root-Cause Remediation Report

Engine version: 1.4.0 -> **1.5.0**
Scope: root-cause remediation only. No new features. No case-specific
hard-coding. The frozen 24-case holdout (`gold_corpus/scientific_validity/
final_holdout_v1/`) was **not** modified and its original blind-run
artifacts (`blind_results.json`, `release_gate_result.json` — accuracy
0.375, release gate FAIL) are unchanged. Per the holdout's own integrity
rule, it is used below only as an **exposed regression set**, never as a
fresh validation estimate.

---

## A. Root-Cause Report

### A.1 — Evidence Direction / Scientific Language Interpretation

**Not confirmed as originally hypothesized.** The direction classifier
was not simply "too conservative" — it had two distinct, provable bugs:

1. **Negation-scope bug (false positive).** `evidence_interpretation.py`
   used a fixed 30-character lookback window to detect a negation cue
   before a positive phrase. Real prose regularly puts the negation cue
   and the positive phrase more than 30 characters apart across a
   subordinate clause — e.g. *"found **no** convincing evidence that ...
   were **effective**"* has "no" and "were effective" ~51 characters
   apart. The fixed window missed this, so genuinely null findings were
   misclassified `positive`.
2. **Vocabulary gap (false "unclear").** Common systematic-review
   phrasing was simply absent from the phrase/regex tables: comparative
   constructions ("X better than placebo"), general recommendation
   language ("good evidence to recommend", "commonly recommended"),
   "reduced `<duration/incidence/severity>`" without the literal word
   "number", and null-finding phrasing explicitly named in the phase
   brief ("insufficient evidence to recommend", "not been shown to
   provide benefit", "did not (consistently) demonstrate an effect").

**Fix:** widened the negation-lookback to the current clause (bounded by
sentence punctuation *and* contrastive conjunctions — "but"/
"although"/"however"/"whereas"/"while"/"yet" — so an earlier negation
cannot wrongly cancel a later, contrastively-introduced positive
finding), and added the missing generic vocabulary in both
`evidence_interpretation.py` and `final_decision_policy.py`'s
`_final_decision_direction` (the actually-authoritative direction
function consumed by `resolve_scientific_evidence`).

**Verified root cause, not accepted on faith:** confirmed via direct
function calls against each failing case's real evidence text before
writing any fix, and re-verified after.

### A.2 — Safety same_plant / self-row behavior

**Root cause is different from the brief's hypothesis.** The
`same_plant` architecture (`eligibility_gate.py`'s `SafetyFinding`/
`classify_safety_finding`) already correctly avoids letting `same_plant`
silently neutralize a genuine SEVERE finding — a prior remediation round
had already added a "serious structured assertion with no
candidate-limiting qualifier defaults to species-wide" rule, independent
of `same_plant`. The actual bug was **upstream**: `safety_assertion_engine
.py`'s extraction regexes were too narrow to ever produce a SERIOUS
structured assertion from real prose in the first place:
- `_ORGAN_TOXICITY` matched singular "liver injury" only, not "liver
  injuries" (real text: *"caused ... hepatocellular **liver injuries**"*).
- `_FATAL_AE` matched "death(s)" but not "**fatalities**" as a noun, and
  required the exact past-tense "caused" rather than tense-flexible
  "cause"/"causes"/"caused" with an adequate word-distance window for
  cases where several intervening symptoms are listed before the fatal
  outcome (*"can **cause** seizures, coma, ..., multiorgan failure and
  **death**"*).
- No standalone recognition for de-facto life-threatening outcome nouns
  ("multiorgan failure", "cardiovascular collapse", "acute hepatic
  necrosis") that inherently denote severe harm regardless of which verb
  introduces them.

**Fix:** widened these regexes (plural forms, present-tense causal verbs,
a `fatalit(?:y|ies)` alternative, and a standalone severe-outcome term
list), entirely inside `safety_assertion_engine.py`. `eligibility_gate.py`
itself needed no change for this problem.

### A.3 — Regulatory generalization / scope (largest failure category, confirmed)

Two independent, confirmed bugs:

1. **Verb-conjugation gap.** `regulatory_barrier_classifier.py` only
   matched the past-participle form of each action word ("prohibited",
   "banned", "outlawed") — present tense ("prohibit", "prohibits", "ban")
   produced zero matches. Two of four regulatory holdout cases used
   present tense and were invisible to the classifier entirely.
2. **Scope-defaulting gap (the true "self-row" issue for regulatory).**
   `eligibility_gate.classify_regulatory_finding()` had **no mechanism at
   all** to ever resolve scope to anything but UNKNOWN in production —
   unlike safety, which had already received the "no qualifier -> species-
   wide by default" fix in an earlier round, regulatory never got the
   analogous treatment. Every PROHIBITED finding, however unambiguous,
   was structurally capped at EXPERT_REVIEW_REQUIRED.
3. A distinct, non-keyword failure mode: a **dose-dependent** restriction
   ("must contain less than 800 mg X per daily portion; proposed portion
   provides 900 mg") is not expressible as phrase-presence at all — it
   requires numeric extraction and comparison, a capability the
   classifier never had.

**Fix:** added verb-conjugation-aware matching
(`scientific_phrase_matcher.find_verb_aware_phrase_matches`), and a new
module `regulatory_scope_assessment.py` providing (a) generic
qualifier-scope matching — a documented prohibition with no
candidate-limiting qualifier (part/preparation/constituent) defaults to
species-wide, applying the identical principle already established for
safety; a qualifier that IS present only resolves to relevant when the
candidate's own declared context independently restates it — and (b) a
plant/compound-agnostic numeric dose-threshold comparator.

### A.9 — Fail-open audit (final decision policy)

**Audited, no live bug found.** Traced every write-site of
`Final_Decision_Status` (exactly two: the per-row authoritative path and
the multi-compound merge path in `botanical_rd_candidate_engine.py`, both
consuming the same `eligibility_gate`/`final_decision_policy` functions —
confirmed by direct grep, not assumption) and every branch of
`final_decision_policy.decide_final()`. UNKNOWN/UNRESOLVED/INCOMPLETE
states are checked and routed to `INSUFFICIENT_EVIDENCE` or
`EXPERT_REVIEW_REQUIRED` *before* the function's only unconditional `GO`
return; `GO` is reachable only when eligibility is `ELIGIBLE` (not
`INCOMPLETE`) and the scientific-evidence signal is `SUPPORTIVE` (not
`INSUFFICIENT`/`UNRESOLVED`/`CONFLICT`/`SUPPORTIVE_WITH_CAUTION`). No
fail-open path to GO was found. This is a genuine finding, not a
skipped task — reported honestly rather than inventing a fix for a bug
that was not actually present.

### A.legacy — Decision_Class vs Final_Decision_Status (dual-authority concern)

Investigated whether `_decision_class()`/`_evaluate_gates()` (the older,
first-computed per-row values) constitute a second decision authority.
Confirmed they do **not**: every row's `Decision_Class` and
`Final_Decision_Status` are unconditionally recomputed and overwritten
during the per-plant merge step
(`botanical_rd_candidate_engine.py::_merge_multi_compound_matches`) from
the same `eligibility_gate`/`final_decision_policy` functions, for every
row (the merge branch is gated only on a column's existence, which is
always populated). `_decision_class()`'s own output only survives into
`Gate_Results` (explicitly documented as informational/non-blocking) and
is never read by any external consumer as the final answer.

---

## B. Architecture Changes

| File | Change |
|---|---|
| `scientific_phrase_matcher.py` | Added `find_verb_aware_phrase_matches` / `_verb_inflection_pattern` — generic English verb-conjugation matching (base/-s/-ed/-ing), additive only, existing functions unchanged. |
| `regulatory_barrier_classifier.py` | Uses the new verb-aware matcher for the "Prohibited/banned" action verbs (prohibit/ban/outlaw); non-verb phrases unchanged. |
| `regulatory_scope_assessment.py` | **New module.** Generic qualifier-scope assessment (`assess_regulatory_scope`) and numeric dose-threshold comparison (`detect_dose_threshold_violation`). No botanical names, PMIDs, or case-specific text anywhere in it. |
| `safety_assertion_engine.py` | Widened `_ORGAN_TOXICITY`/`_FATAL_AE` regex vocabulary (plural forms, tense-flexible causal verbs, "fatalities" noun form, standalone severe-outcome terms). |
| `eligibility_gate.py` | `classify_regulatory_finding()` now accepts `candidate_context_text`, wires in the new scope-assessment and dose-threshold detection, and defaults an unqualified prohibition to species-wide scope (mirrors the existing safety-side default). |
| `botanical_rd_candidate_engine.py` | Wires `candidate_context_text`/finding text through to both real `classify_regulatory_finding()` call sites (per-row and merge-step) via two new internal-only row fields (`_candidate_indication_text`, `_regulatory_finding_text`, dropped before final output — same pattern already used for `_same_plant`/`_match_quality`). `DECISION_ENGINE_VERSION` bumped 1.4.0 -> 1.5.0 with full changelog entry. |
| `evidence_interpretation.py` | Negation-lookback widened from a fixed 30 chars to clause-scope (sentence punctuation + contrastive conjunctions). Added missing generic positive/null vocabulary. |
| `final_decision_policy.py` | Added a small number of generic phrases to `_final_decision_direction`'s existing UNCLEAR-widening lists (the function already had this mechanism; this only extends its vocabulary, no new mechanism). |
| `test_gate_layer.py`, `test_gold_case_execution.py`, `test_phase4_eligibility_gate_desired_behavior.py` | Updated 3 tests that asserted the OLD (pre-remediation) regulatory-scope-defaulting behavior as correct; each now documents, with inline justification, why the corrected behavior is right. No assertion was weakened — each still requires an exact, specific outcome. |
| `test_task15_decision_engine_version_tracking.py`, `test_task16_plant_profile_regulatory_integrity.py`, `test_task17_plant_profile_evidence_freshness.py` | Version-lock literal updated 1.4.0 -> 1.5.0. |
| `test_reference_grounded_validation_v1_remediation.py` | **New.** 20 synthetic regression tests (invented plant/compound names, never the holdout's own wording) proving each root-cause fix generalizes. |

**Explicitly not changed:** `regulatory_barrier_classifier.py`'s non-verb
phrase list, `_hard_safety_gate()`/`_hard_regulatory_gate()` (legacy,
informational-only), any scoring weight or threshold, any Gold Case
fixture, the frozen holdout itself.

---

## C. Tests

Full suite before this phase: 2881 passed, 0 failed, 3 xfailed.
Full suite after this phase: **2901 passed, 0 failed, 3 xfailed**
(2881 existing + 20 new regression tests, zero existing tests weakened;
3 pre-existing characterization tests updated with justification as
described above).

## D. Exposed Regression Results (NOT independent validation)

Per the holdout's own integrity rule, the 24 cases are **exposed** and
this is a **regression re-run only**, not a fresh validity estimate.

| Metric | Original blind run (frozen) | Regression after v1.5.0 |
|---|---|---|
| Accuracy | 0.375 (9/24) | 0.958 (23/24) |
| Macro-F1 | 0.416 | 0.958 |
| Serious safety false negatives | 2 | **0** |
| Regulatory false negatives | 4 | **0** |
| GO recall | 0.25 | 1.00 |
| GO WITH CAUTION recall | 0.50 | 1.00 |
| EXPERT REVIEW REQUIRED recall | 0.25 | 0.75 |
| NO GO SAFETY recall | 0.50 | 1.00 |
| NO GO REGULATORY recall | 0.00 | 1.00 |
| INSUFFICIENT EVIDENCE recall | 0.75 | 1.00 |

The one remaining miss (`rgv1_012_garcinia_weight`, expected EXPERT
REVIEW REQUIRED, actual INSUFFICIENT EVIDENCE) is discussed under
Remaining Scientific Risks below — it was deliberately not force-fixed.

The frozen original artifacts (`blind_results.json`,
`release_gate_result.json`, `FINAL_REFERENCE_GROUNDED_VALIDATION_REPORT.md`)
are unmodified and still show the original 0.375 FAIL result, as they
must — this table exists only in this report.

## E. Remaining Scientific Risks

1. **Garcinia-style "may cause `<desired outcome>`" phrasing.** Evidence
   text such as *"may cause short-term weight loss, but the magnitude
   was small and clinical relevance uncertain"* is genuinely ambiguous
   for a generic classifier: "cause" is used throughout the safety
   vocabulary specifically to introduce **harm** ("can cause seizures,
   coma..."), so a blanket "X may cause Y -> positive" rule would create
   a direct, dangerous conflict with the safety-direction literature.
   This was deliberately left unresolved rather than risk that
   regression. A real fix would need outcome-desirability context (is
   the "caused" outcome the therapeutic goal or a harm?) that the
   current architecture does not model — flagged as a genuine
   architecture gap, not a vocabulary gap.
2. **Numeric dose-threshold comparator is a first version.** It handles
   the "less than / no more than / maximum of X `<unit>`" family and
   mg/mcg/g units. It does not yet handle percentage-based limits,
   per-kg-bodyweight dosing, or ranges ("between X and Y mg"). It was
   validated against the one dose-based case in the holdout plus
   synthetic positive/negative/no-data-found controls, not against a
   broader corpus of real EU regulatory dose text.
3. **Regulatory qualifier-scope matching is lexical, not semantic.** It
   confirms relevance only when the candidate's own declared context
   text independently restates the same qualifier phrase found in the
   regulatory source. A genuine match expressed in different words on
   each side (e.g. "hydroxyanthracene derivatives" vs. "anthraquinone
   glycosides", which may be the same chemical class under different
   naming) would not be detected and would conservatively fall to
   EXPERT_REVIEW_REQUIRED rather than NO_GO_REGULATORY — a safe failure
   direction, but a real precision limitation worth knowing.
4. **EXPERT REVIEW REQUIRED recall (0.75, 3/4) is the lowest-scoring
   class on the regression set.** The one miss is the Garcinia case
   above; no other EXPERT_REVIEW-class regression was found, but the
   sample size (4 cases) is too small to generalize confidently.

## F. Next Validation Plan

Per the holdout's own integrity rule, `final_holdout_v1`'s 24 cases must
never again be used as an independent accuracy estimate — they are now
permanently a regression set only (and are included, unmodified, in
`test_reference_grounded_validation_v1_remediation.py`'s spirit, though
not literally re-run as a pytest assertion, to avoid overfitting the
suite to this specific set).

Recommended before claiming "reference-grounded validated" for 1.5.0:

1. Freeze a **new, independent** holdout (different botanicals/PMIDs/
   regulatory citations than both the original 6 Gold Cases and this
   24-case set), same balanced 4-per-class design, built and frozen
   before running the engine against it.
2. Include deliberately-adversarial cases for the four confirmed root
   causes: present-tense regulatory verbs, plural/alternate-phrasing
   safety harm language, dose-threshold restrictions with a *compliant*
   (non-violating) dose (to confirm no over-triggering), and evidence
   direction phrasing using contrastive conjunctions ("but", "although")
   to confirm the clause-scoped negation fix doesn't over-cancel.
3. Re-run the full pytest suite and confirm 0 failures immediately before
   freezing the new holdout, so the frozen run reflects exactly the code
   that will be evaluated.
4. If accuracy/macro-F1/zero-false-negative gates pass on the new
   holdout, that is the first legitimate "reference-grounded validated"
   claim for this architecture — the 0.958 regression number above must
   not be cited as that claim, since the engine's remediation was
   informed by (though not directly fit to) this exposed set.
