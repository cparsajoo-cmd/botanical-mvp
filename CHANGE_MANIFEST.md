# CHANGE_MANIFEST.md — Pre-Investor Reliability Repair

Scope actually delivered in this pass: **Defects 1, 3, 4, 5, 6, 7** from the
cahier, root-caused against the real code and verified against the real test
suite. **Defects 2, 8, 9, 10 were not started** — see "Remaining scientific
limitations" at the end of this document for why, and what they need.

No plant or indication name is hard-coded anywhere in these fixes. All
changes generalize to arbitrary indications/botanicals, per the cahier's
rules 1–2.

---

## 1. `phase5_scoring_config.py`

**Defects addressed:** 1, 3, 6

**Functions/constants changed:** module-level constants only (no functions).

- Added `INSUFFICIENT_DIRECTION_DATA` status constant with entries in
  `DIRECTION_FACTORS` (0.00 — no positive direction credit) and
  `CONSISTENCY_FACTORS` (0.70, same as `INSUFFICIENT`).
  - **Before:** only 7 consistency states existed; a tier with evidence but
    no resolved result direction had no honest state to fall into.
  - **After:** a distinct, explicit state exists for "evidence exists, but
    none of it has a resolved direction" — separate from `INSUFFICIENT`
    (no evidence at all) and never `MIXED` (a genuine disagreement).

- Added `TARGET_UNSPECIFIED` status constant, deliberately **absent** from
  `APPLICABILITY_FACTORS` (excluded from aggregation, like
  `NOT_APPLICABLE`).
  - **Before:** only `MATCH/PARTIAL/UNKNOWN/MISMATCH/NOT_APPLICABLE`
    existed; a target dimension the project never specified had no
    distinct status from a dimension the evidence simply didn't report.
  - **After:** a project-incompleteness signal exists that does not
    penalize `Record_Applicability_Factor`.

- `MARKET_STATUS_POINTS["Search incomplete"]`: **3.0 → 0.0**.
  - **Before:** an incomplete market search scored a positive +3 bonus,
    directly contradicting the comment immediately above its only call
    site (`botanical_rd_candidate_engine.py`), which already said this
    case should get "the same neutral treatment as not performed, not a
    bonus."
  - **After:** neutral (0.0), matching that comment and matching
    `market_neutral_default`.

**Tests added/changed:** none directly (covered by callers' tests below).

---

## 2. `evidence_consistency.py`

**Defect addressed:** 1 (unreported evidence treated as mixed efficacy)

**Function changed:** `classify_evidence_consistency()`. New function added:
`direction_data_completeness()`.

- **Before:** `unreported`-direction records stayed in the ratio
  denominator (`positive/total`, `(harmful+null)/total`), diluting the
  ratios. A tier that was genuinely unanimous among its KNOWN-direction
  records could still fall through every threshold and hit the catch-all
  `return MIXED` purely because it also contained several records whose
  direction was never extracted.
- **After:** ratios are computed only over `known_direction_total =
  positive+null+harmful+mixed` (unreported excluded from the denominator,
  but still counted toward `total` — nothing is silently discarded). If
  `known_direction_total == 0` while `total > 0`, the function now returns
  the new `INSUFFICIENT_DIRECTION_DATA` state instead of falling through to
  `MIXED` or defaulting to a positive class. `unreported` records are never
  counted as positive.
- New `direction_data_completeness(profile)` returns `"PARTIAL"` when any
  record's direction is unresolved, `"COMPLETE"` otherwise — a separate,
  purely informational signal (requirement D), never consumed by the
  classifier itself.

**Tests changed:**
`test_phase5_scoring_calibration_addendum.py::test_phase5_unreported_outcomes_do_not_manufacture_mixed_classification`
(renamed from `..._remain_in_consistency_denominator`, which asserted the
literal defect) and
`test_phase5_scoring_calibration_addendum.py::test_phase5_consistency_distinguishes_no_records_from_unreported_records`
now assert the corrected `CONSISTENT_POSITIVE` / `INSUFFICIENT_DIRECTION_DATA`
outcomes instead of the old `MIXED` outcomes.

---

## 3. `candidate_shortlisting.py`

**Defects addressed:** 1, 4, 5, 6, 7, 9 (partial)

### `_mechanism_support()` — Defect 4
- **Before:** `2.0 × count(Supported_Target_or_Mechanism == True)` rows,
  capped at 10 — pure row-volume scoring. Production: 10/10 for 49/51
  candidates.
- **After:** `2.0 × len(_indication_specific_mechanism_values(...))` —
  counts **unique, indication-relevant** mechanism components (reusing the
  existing de-duplication/indication-filtering helper, not new semantic
  logic), capped at 10.

### `_compound_quality()` — Defect 5
- **Before:** the base compound score already de-duplicated by compound
  name (`max()`), but the "linked to a supported mechanism" bonus summed
  `row_weight` per matching ROW with no de-duplication — the actual source
  of the 44/51 saturation to 5/5.
- **After:** the bonus is now de-duplicated by compound name using the same
  `max()`-based pattern as the base score (`best_linked_by_name`).

### `_novelty_market()` — Defect 6
- **Before:** unassessed/unavailable/not-performed commercial status
  returned **2.5** points, directly contradicting the function's own
  docstring ("Missing market data earns zero points... 'not searched' is
  not an opportunity"). Also expanded `_COMMERCIAL_UNASSESSED_TERMS` to
  include `"unknown"`, `"skipped"`, `"search incomplete"` — states the
  observed production run actually reported that weren't previously
  covered.
- **After:** returns **0.0**.

### `_safety_regulatory()` — Defect 7
- **Before:** "no safety info" → 5.0 points; "no regulatory info" → 3.0
  points — up to 8/15 for knowing nothing at all.
- **After:** both branches return 0.0. Return signature extended to
  `(points, tier, prohibitive)` — see the gate fix below.

### Plant-status gate (line ~3270) — Defect 7 side effect, caught by the
real test suite
- **Before:** `if safety_reg_points <= 0.0: plant_status = "Excluded"`.
  Harmless while "no info" scored 8.0 (never triggered this branch). Once
  "no info" correctly dropped to 0.0, this gate started silently
  auto-excluding candidates with **no known safety/regulatory signal at
  all** — exactly the anti-pattern the cahier explicitly warned against.
- **After:** `_safety_regulatory()` now returns an explicit `prohibitive`
  boolean (true only for a plant-level hard stop, a severe safety term, or
  an explicit regulatory prohibition). The gate now checks
  `if safety_reg_prohibitive:` instead of the ambiguous `<=0.0` comparison.
  An honestly-unknown candidate scores 0 safety points and is no longer
  auto-excluded, but still requires review before Go (unchanged
  `eligibility_gate.py` behavior).

### `_outcome_profile()` / `_outcome_profile_from_row_records()` — Defects 1 & 9
- **Before:** each function computed its own independent `label` heuristic
  that did NOT count `unreported` records toward a "mixed" verdict — a
  DIFFERENT rule from `classify_evidence_consistency()`'s (which did count
  them, per the defect-1 bug above). This is the literal mechanism behind
  the reported Valerian contradiction: `Primary_Tier_Outcome_Label` =
  "Predominantly positive results" while `Evidence_Consistency_Class` =
  "MIXED", from the same underlying counts.
- **After:** both functions call `classify_evidence_consistency()` on their
  own counts and map the result through a single
  `_CONSISTENCY_CLASS_TO_OUTCOME_LABEL` dict. `Primary_Tier_Outcome_Label`
  (and the diagnostic-only `All_Tier_Outcome_Consistency_Diagnostic`) can no
  longer disagree with `Evidence_Consistency_Class` for the same input,
  because they are now the same computation. `MOSTLY_POSITIVE` is mapped to
  "Mixed/inconsistent results" (not "Predominantly positive"), reserving
  that label for the near-unanimous `CONSISTENT_POSITIVE` case.
  `evidence_direction_profile` also gained a new, additive
  `Direction_Data_Completeness` field.

  This resolves the *specific, verified* contradiction mechanism for
  Primary_Tier_Outcome_Label vs. Evidence_Consistency_Class. It does **not**
  resolve the separate `Indication_Evidence_Direction` field, which comes
  from a wholly different subsystem (`evidence_adjudication_engine.py`,
  AI-adjudicated) — that is Defect 9's remaining, larger scope; see
  "Remaining scientific limitations."

### Applicability aggregation (`_scientific_evidence_components()`) — Defect 3
- Propagates the new `Target_Definition_Completeness` signal from
  `evaluate_applicability()` (see `standard_evidence_builder.py` below)
  across a candidate's primary-tier records (`any_target_incomplete`) and
  exposes it on the returned dict and on `Plant_Applicability_Factor`'s
  sibling fields. Not yet wired into a final Go/decision gate (see
  limitations).

**Tests changed:** `test_candidate_shortlisting.py` —
`test_missing_safety_and_regulatory_data_is_not_scored_as_clean` (8.0 →
0.0), `test_explicit_safety_and_market_information_create_real_differentiation`
(2.5 → 0.0). **Tests added:**
`test_duplicate_mechanism_rows_do_not_saturate_mechanism_support`,
`test_unrelated_mechanisms_do_not_score_for_requested_indication`,
`test_several_distinct_mechanisms_score_higher_than_one_duplicated_mechanism`,
`test_duplicate_compound_rows_do_not_inflate_linked_mechanism_bonus`.

---

## 4. `standard_evidence_builder.py`

**Defect addressed:** 3 (applicability collapsing to 0.60)

**Function changed:** `evaluate_applicability()`.

- **Before:** any dimension in `Required_Transferability_Dimensions` that
  the TARGET/PROJECT itself never specified was converted from
  `NOT_APPLICABLE` to `UNKNOWN` — the identical status used when the target
  DID specify a dimension but the EVIDENCE record failed to report it. Both
  were then `min()`-ed into `Record_Applicability_Factor` identically. A
  project that only specified preparation + indication would have
  plant_part/route/dose forced to `UNKNOWN` (factor 0.60) and drag a
  perfectly-matching-preparation record down to 0.60 regardless.
- **After:** that conversion now targets a new `TARGET_UNSPECIFIED` status,
  excluded from the factor/classification aggregation entirely (same
  treatment as `NOT_APPLICABLE`). A dimension the target DID specify but
  the evidence doesn't report still becomes genuine `UNKNOWN` (unchanged,
  still penalizes the factor) — the comparator functions
  (`_appl_dimension_simple/_preparation/_dose/_indication`) already
  distinguished these cases correctly; only the post-hoc "required but
  blank" loop was conflating them. New `Target_Definition_Completeness`
  field ("incomplete"/"complete") surfaces the target-side gap separately,
  so it can still inform a "fully transferable" decision downstream without
  corrupting the evidence-transferability score itself.

**Tests changed:**
`test_preparation_transferability_invariants.py::test_capsule_is_dosage_form_not_automatically_a_preparation_and_missing_context_is_not_full_match`
now asserts `Applicability_Classification == "MATCH"` and
`Record_Applicability_Factor == 1.0` (was `"UNKNOWN"`/`< 1.0`), plus checks
the new `Target_Definition_Completeness == "incomplete"` and each
unspecified dimension's status.

**Tests added:**
`test_target_unspecified_dose_and_part_do_not_mask_a_preparation_mismatch`
(the cahier's exact Defect-3 acceptance test — a project specifying only
infusion + indication must still distinguish a matching-preparation record
from a mismatched one, neither forced to 0.60) and
`test_target_specified_but_evidence_silent_stays_unknown_not_target_unspecified`
(regression: when the target DOES specify a dimension but the evidence
doesn't report it, it must stay genuine `UNKNOWN`, factor 0.60 — unchanged).

---

## 5. Test files touched only to correct hard-coded pre-fix values

These encoded the exact numeric/behavioral defects being fixed (confirmed
by reading each one before changing it — none were changed to make new
*incorrect* behavior pass):

- **`test_scoring_config.py`** —
  `test_default_scoring_config_field_values_match_documented_pre_task_weights`:
  `config.market_search_incomplete == 3` → `== 0` (defect 6).
- **`test_step5_scientific_result_preparation_safety.py`** —
  `test_go_requires_positive_results_compatible_preparation_and_explicit_safety`:
  literal `Overall_Score == 77.8` → `== 68.5`. Verified this is pure
  numeric drift from the corrected (de-saturated) Mechanism/Compound/
  Safety/Novelty components on this fixture; the fixture's own
  Applicability/indication-UNKNOWN reasoning (documented in its docstring)
  and its `Go_Investigate_Hold_NoGo == "Investigate"` outcome are
  unaffected.
- **`test_phase5_scoring_calibration_addendum.py`** —
  `test_phase5_lower_tiers_cannot_change_a_primary_tier_go_decision`:
  `Go_Investigate_Hold_NoGo == "Go"` → `== "Investigate"` (both instances).
  Verified this fixture's `COX-2 inhibition` mechanism term has no textual
  link to its `"test indication"` label (so 0 indication-specific mechanism
  credit is correct, not a regression) and it supplies no real market/
  regulatory data (so both correctly score 0 instead of the old inflated
  2.5/3.0). The score dropped from the platform's previous **inflated**
  82.2 to a correctly-scored 65.9, legitimately below the Go threshold
  (78.0). The actual invariant this test protects — that diagnostic-only
  lower-tier records cannot change the primary-tier decision — is
  unaffected and still verified (both runs still produce the same decision
  and the same primary-tier scores).

---

## Remaining scientific limitations

Not fixed in this pass — flagged explicitly rather than claimed done:

- **Defect 2** (outcome-specific human evidence vs. indication relevance
  authority mismatch — e.g. near-maximal DIRECT HUMAN relevance with zero
  verified human outcome evidence) — not investigated. Needs root-causing
  across `general_indication_relevance.py`, `indication_candidate_discovery.py`,
  and `evidence_adjudication_engine.py`.
- **Defect 8** (`_derive_decision_class_ah()`'s "B — Established scientific
  candidate" label derived from `Overall_Score` alone) — not investigated.
  `_derive_go_call()` already gates "Go" on dosage compatibility + explicit
  reassuring safety + a positive-results outcome label in addition to the
  score threshold, which is a partial mitigation, but
  `_derive_decision_class_ah()`'s "Established" label uses the score
  threshold alone with no equivalent evidence gate. Needs the same
  evidence-conditions treatment applied to `_derive_go_call()`.
- **Defect 9** (single authority hierarchy across `Indication_Evidence_Direction`,
  `Outcome_Consistency`, `Evidence_Consistency_Class`, `Human_Evidence_Strength`,
  AI counts, and strict outcome-specific counts) — only partially addressed.
  `Primary_Tier_Outcome_Label` and `Evidence_Consistency_Class` can no
  longer disagree with each other (fixed, see `candidate_shortlisting.py`
  above). `Indication_Evidence_Direction` is a wholly separate,
  AI-adjudicated field computed in `evidence_adjudication_engine.py` and
  was not touched — it can still disagree with the scientific-evidence-
  pipeline's own direction/consistency fields. This needs an explicit,
  documented precedence audit across both subsystems, which is a
  substantially larger investigation than fit in this pass.
- **Defect 10** (fail-gracefully audit across Step 2–6 execution/UI paths)
  — not investigated in this pass.
- **`Target_Definition_Completeness`** (new field from the Defect 3 fix) is
  computed and exposed on the applicability result and on
  `_scientific_evidence_components()`'s output, but is **not yet wired**
  into any final "Go"/"fully transferable" decision gate — it is currently
  informational only. The cahier's requirement that an unspecified target
  dimension "may prevent a final Go... conclusion" is therefore only
  half-delivered: the score no longer takes an unjustified penalty, but
  nothing yet uses the completeness signal to require target-definition
  completeness before Go. This is the same "computed but not wired into
  authoritative_fields/decision logic" trap this codebase has hit several
  times before (see project history — RD_Discovery_Lane, Mechanistic_
  Evidence_Record_IDs) and should be checked for on the next pass.
- The model's overall reliability posture is unchanged from prior external
  reviews: this pass fixes the specific scoring-component defects in the
  cahier, not the platform's broader evidence-adjudication architecture.
  `SCORING_MODEL_VERSION`/`PROVISIONAL_NOTICE`/`RANKING_CALIBRATION_STATUS`
  continue to apply — the model remains a provisional R&D prioritization
  score, not a validated efficacy or clinical-success probability.
