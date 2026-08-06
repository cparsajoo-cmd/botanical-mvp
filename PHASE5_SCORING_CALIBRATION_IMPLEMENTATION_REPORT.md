# Phase 5 — Scientific Score Calibration: Implementation Report

Implements the audit contract in `PHASE5_SCORING_CALIBRATION_AUDIT.md` and
`PHASE5_SCORING_CALIBRATION_AUDIT_ADDENDUM.md` (Round 7, supervisor-approved).
No production code was patched to force artificial test passes — every
desired-behavior test now passes because the underlying architecture
(tier precedence, Direction/Consistency classification, evidence-vs-target
applicability, deterministic narrative provenance) is genuinely implemented,
traceable from one `EvidenceRecord` through to the plant-level authoritative
output, using the exact fixtures already specified in the test file.

---

## 1. Files Changed

### Production files (new)
- `phase5_scoring_config.py` — the single central location for every
  Phase 5 constant/threshold (`SCORING_MODEL_VERSION`,
  `EVIDENCE_TIER_PRECEDENCE`, `HIERARCHY_LABEL_TO_TIER`,
  `DIRECTION_FACTORS`, `CONSISTENCY_FACTORS`, `APPLICABILITY_FACTORS`,
  `MARKET_STATUS_POINTS`). Every other module imports from here; nothing
  is copied.
- `evidence_consistency.py` — `classify_evidence_consistency(profile)`,
  an independent, directly-testable helper mapping an outcome-count
  profile to one of the seven consistency classes. The supervisory
  correction pass now keeps `unreported` records in the denominator,
  uses an explicit `profile["total"]` when supplied, rejects internally
  inconsistent totals, and distinguishes a non-empty all-unreported pool
  (`MIXED`) from zero records (`INSUFFICIENT`).

### Production files (modified)
- `standard_evidence_builder.py` — added `evaluate_applicability(evidence_row,
  target_context)` and its per-dimension helpers (species/plant_part/route:
  simple equality; preparation: deterministic parent-category rule with a
  legacy `Preparation_Applicability`/`Dosage_Form_Compatibility` adapter;
  dose: unit-matched range comparison; indication: reuses the existing
  authoritative `Indication_Match_Type`). No existing function in this
  module (`build_scientific_evidence`, `build_standard_evidence`, etc.)
  was changed.
- `botanical_rd_candidate_engine.py` — `ScoringConfig`'s market-signal
  fields now source their default values from
  `phase5_scoring_config.MARKET_STATUS_POINTS` instead of local literals;
  `market_neutral_default` corrected from `+3` to `0.0` (the confirmed
  defect, main audit §3.1). No other field, weight, or scoring branch in
  this file changed.
- `candidate_shortlisting.py` — the core of the implementation:
  - `_evidence_quality()`'s existing `row_records` (already computed for
    the authority/hierarchy weighting) is now also exposed via its
    `explain` dict, reused rather than re-derived.
  - New `_scientific_evidence_components()`: tier assignment (reusing
    `row_hierarchy_points()`'s existing label, never re-classifying study
    design), primary-tier selection, tier-restricted outcome profile,
    `classify_evidence_consistency()`, `Direction_Factor`/`Evidence_
    Consistency_Factor` lookup, per-record `evaluate_applicability()`
    calls restricted to the primary tier, quality-weighted
    `Plant_Applicability_Factor`, deterministic narrative-provenance
    selection, and the final multiplicative `Scientific_Evidence_Score`.
  - Supervisory correction: Evidence Quality is now recomputed with the
    unchanged Phase-3 formula over **primary-tier records only**, using the
    already-built/deduplicated `row_records`; lower tiers are score-inert
    and remain visible only in supporting-tier/all-tier diagnostics.
  - Supervisory correction: plant gates and `Go_Investigate_Hold_NoGo`
    now consume `Primary_Tier_Outcome_Profile`, not the tier-blind
    all-record outcome profile.
  - Supervisory correction: `Component_Source_Record_IDs` records the
    actual source IDs consumed by each of the six published score
    components; `Authoritative_Source_Record_IDs` is their deterministic
    union rather than only the empirical Scientific-Evidence subset.
  - `_indication_relevance_detail_authoritative()` and its legacy-fallback
    sibling: the `_outcome_profile()`-based discount removed from both
    (Direction no longer affects Indication Relevance).
  - `build_plant_candidate_shortlist()`: new keyword-only `target_context`
    parameter (backward-compatible; existing positional/keyword call
    sites unaffected); `Overall_Score`/`Score_Breakdown` now use
    `Scientific_Evidence_Score` instead of raw `Evidence_Quality_Score`;
    ~15 new output columns (below).
  - `merge_authoritative_scores()`: narrative-row selection now matches
    `Authoritative_Narrative_Source_Record_ID` against the raw row's own
    `Source_Record_IDs` first (deterministic), falling back to the old
    highest-raw-score selection only when that field is absent —
    documented, not silent. `Scoring_Model_Version` stamped on every row
    unconditionally.
- `score_breakdown_schema.py` — `"Evidence Quality"` renamed to
  `"Scientific Evidence"` in `AUTHORITATIVE_CANONICAL_SECTIONS` and
  `COMPONENT_TO_DIMENSIONS`, matching the new `Score_Breakdown` key.

### Test files (modified — characterization tests converted to
regression tests, per the brief's explicit instruction; every change
documented in-place with the old assertion, why it changed, and what
replaced it)
- `test_gate_layer.py` — 3 hardcoded `R&D_Opportunity_Score` values
  (38.0/23.0 → 35.0/20.0) updated for the market-neutral-default fix.
- `test_occurrence_seed.py` — 1 hardcoded value, same fix.
- `test_scoring_config.py` — 2 hardcoded values (same fix) plus the
  `ScoringConfig` field-value assertion (`market_neutral_default == 3`
  → `== 0.0`).
- `test_step5_scientific_result_preparation_safety.py` — 2 tests
  converted:
  - `test_null_human_evidence_cannot_be_go_or_high_relevance`: old
    assertion (`Indication_Relevance_Score <= 15`) relied on the
    now-removed Direction-in-Indication-Relevance mechanism; converted
    to assert Indication_Relevance is now IDENTICAL to the positive-
    evidence case, and that `Evidence_Consistency_Class`/
    `Direction_Factor`/`Scientific_Evidence_Score` (CONSISTENT_NULL /
    0.00 / 0.00) carry the same protection in the correct place.
  - `test_go_requires_positive_results_compatible_preparation_and_explicit_safety`:
    old assertion (`Go_Investigate_Hold_NoGo == "Go"`) no longer holds
    because this fixture never supplies `Indication_Match_Type`, so the
    `indication` applicability dimension is honestly `UNKNOWN` rather
    than assumed `MATCH` — `Plant_Applicability_Factor` becomes 0.60,
    dropping `Overall_Score` to 77.8 (just under the 78 Go threshold).
    Converted to assert the new, correct values (`Overall_Score == 77.8`,
    `Go_Investigate_Hold_NoGo == "Investigate"`, explicit
    `Dimension_Status` check) with a full explanation of why this is the
    intended consequence of Applicability now being genuinely wired into
    scoring, not a defect.

### New files (deliverables of this report)
- `PHASE5_SCORING_CALIBRATION_IMPLEMENTATION_REPORT.md` (this file)
- `PHASE5_TEST_RESULTS.md`

---

## 2. Architecture Implemented

```
EvidenceRecord (raw row)
  │
  ├─ _build_evidence_row_records() ──► one deduplicated row_record per
  │                                    independent empirical source
  │                                    (authority classified once)
  │
  ├─ _scientific_evidence_components(row_records, target_context)
  │    │
  │    ├─ Step 1: tier assignment (HIERARCHY_LABEL_TO_TIER, reused from
  │    │          the same _row_hierarchy_points() label)
  │    ├─ Step 2: primary tier = highest non-empty in A1→A2→A3→B→C
  │    ├─ Step 3: unchanged Evidence Quality formula over PRIMARY tier only
  │    ├─ Step 4: tier-restricted outcome profile → classify_evidence_
  │    │          consistency() → Evidence_Consistency_Class
  │    ├─ Step 5: Direction_Factor / Evidence_Consistency_Factor (lookup)
  │    ├─ Step 6: evaluate_applicability(record, target_context) per
  │    │          PRIMARY-TIER record only → Record_Applicability_Factor
  │    ├─ Step 7: Plant_Applicability_Factor = quality-weighted mean
  │    │          (weight = existing weighted_points, no new weighting)
  │    └─ Step 8: Scientific_Evidence_Score = Evidence_Quality_Score
  │               × Direction_Factor × Evidence_Consistency_Factor
  │               × Plant_Applicability_Factor, clipped [-6, 30]
  │
  ├─ Overall_Score = Indication_Relevance + Scientific_Evidence_Score
  │                   + Compound + Mechanism + Safety/Regulatory + Novelty
  │                   (Indication_Relevance no longer reads Direction)
  │
  ├─ Primary_Tier_Outcome_Profile drives efficacy gates and Go/Hold
  │  (all-tier profile retained as diagnostic only)
  │
  ├─ Component_Source_Record_IDs tracks each score component's consumed rows
  │  and Authoritative_Source_Record_IDs is their sorted union
  │
  └─ merge_authoritative_scores(): narrative row selected via
     Authoritative_Narrative_Source_Record_ID (deterministic), falls
     back to old raw-score selection only when absent
```

### Old behavior → New behavior

| Aspect | Old | New |
|---|---|---|
| Direction's effect on `Overall_Score` | Applied inside `Indication_Relevance` (conceptually misplaced; tier-blind — animal-tier volume could outvote human-tier direction) | Applied only via `Scientific_Evidence_Score`'s `Direction_Factor`, computed from the primary tier ONLY |
| Evidence tiering | Flat "human" bucket (review + RCT + observational all pooled) | 5 strict levels (A1 review/meta → A2 RCT → A3 other human → B animal → C preclinical/analytical) |
| Mixed-only evidence pool | Fell through to full, undiscounted credit | Classifies `MIXED` → `Direction_Factor = 0.40`, a real discount |
| Applicability | No evidence-vs-target comparison existed; dosage/preparation only affected `Scientific_Triage_Score`, never `Overall_Score` | `evaluate_applicability()` compares every dimension against an explicit `target_context`; `Plant_Applicability_Factor` is one of `Scientific_Evidence_Score`'s four multiplicative terms |
| Market "Unknown"/"Search not performed" | `+3`, scored ABOVE a verified positive finding (`+1`) | Neutral `0.0` |
| Narrative row selection | Highest raw, pre-merge `R&D_Opportunity_Score` across ALL rows (could describe different evidence than the published score) | `Authoritative_Narrative_Source_Record_ID`, the richest record WITHIN the primary tier that established the score |
| `Score_Breakdown` evidence key | `"Evidence Quality"` (raw, unsigned, direction/applicability-blind) | `"Scientific Evidence"` (backed by `Scientific_Evidence_Score`) |

---

## 3. Score Formula

```
Scientific_Evidence_Score =
    Evidence_Quality_Score        (0..30, unsigned — UNCHANGED formula)
    × Direction_Factor            (-0.20 .. 1.00)
    × Evidence_Consistency_Factor ( 0.60 .. 1.00)
    × Plant_Applicability_Factor  ( 0.25 .. 1.00, weighted mean, primary tier)

Range: -6.0 .. 30.0

Overall_Score = Indication_Relevance + Scientific_Evidence_Score
              + Compound_Support + Mechanism_Support
              + Safety_Regulatory + Novelty_Market
```

All weights, thresholds, and the tier/classification mapping are defined
exactly once, in `phase5_scoring_config.py`.

`SCORING_MODEL_VERSION = "phase5-scientific-score-v1.0.0-provisional"`,
present on every authoritative output row (`Scoring_Model_Version`).

---

## 4. New Output Fields (authoritative plant-level result)

`Scientific_Evidence_Score`, `Direction_Factor`, `Evidence_Consistency_Class`,
`Evidence_Consistency_Factor`, `Evidence_Direction_Profile` (nested:
`Primary_Evidence_Tier`, `Primary_Tier_Record_Count`,
`Evidence_Consistency_Class`, `Direction_Factor`), `Plant_Applicability_Factor`,
`Applicability_Factor` (backward-compat alias of the above),
`Record_Applicability_Summary` (per-source-record-ID `Dimension_Status`/
`Record_Applicability_Factor`), `Dimension_Status` (plant-level, worst-
status-wins aggregate over the primary tier), `Applicability_Classification`,
`Applicability_Data_Completeness`, `Primary_Evidence_Tier`,
`Supporting_Evidence_Tiers_Present`, `Supporting_Evidence_Record_Count`,
`Primary_Tier_Outcome_Profile`, `Primary_Tier_Outcome_Label`,
`All_Tier_Evidence_Quality_Diagnostic`,
`All_Tier_Outcome_Consistency_Diagnostic`,
`Scoring_Model_Version`, `Authoritative_Source_Record_IDs`,
`Component_Source_Record_IDs`,
`Authoritative_Narrative_Source_Record_ID`, `Authoritative_Narrative_Provenance`.

`standard_evidence_builder.evaluate_applicability()` (record-level, callable
directly) returns `Dimension_Status`, `Applicability_Classification`,
`Record_Applicability_Factor`, `Applicability_Factor` (alias), and
`Applicability_Data_Completeness`.

---

## 5. Backward Compatibility

- `build_plant_candidate_shortlist(raw_df, *, indication="", dosage_form="",
  max_candidates=50, target_context=None)` — every existing call site
  (verified in this correction sandbox: full test suite, 2509 tests,
  zero collection errors, using external test-only dependency stubs as
  documented in §9) that
  never passes `target_context` continues to work; `indication`/
  `dosage_form` still populate `Target_Indication`/`Target_Preparation`
  when `target_context` doesn't specify them; explicit `target_context`
  values always win.
- `R&D_Opportunity_Score = Overall_Score` alias preserved exactly.
- `Score_Breakdown`'s `"Evidence Quality"` key is gone (renamed to
  `"Scientific Evidence"`) — this is a genuine, intentional field-name
  change (per the brief's explicit instruction), not an oversight; any
  external caller reading that specific dict key by name will need to
  update it. `score_breakdown_schema.py`'s `AUTHORITATIVE_CANONICAL_SECTIONS`
  was updated to match, so `parse_score_breakdown()` still round-trips.
- `Evidence_Quality_Score` (the raw, unsigned column) is unchanged and
  still present.
- Legacy rows lacking `Evidence_Species`/`Evidence_Preparation`/
  `Indication_Match_Type` resolve those dimensions to `NOT_APPLICABLE`
  (no `target_context` at all) or `UNKNOWN` (dimension requested but
  data absent) — never a fabricated `MATCH`. The one legacy-field adapter
  implemented: `Preparation_Applicability`/`Dosage_Form_Compatibility`
  (`"Compatible"`/`"Mismatch"`) maps directly to `MATCH`/`MISMATCH` for
  the `preparation` dimension when `Evidence_Preparation` itself is
  absent, reusing the existing pre-Phase-5 signal rather than requiring
  every legacy row to be re-annotated.

---

## 6. Known Provisional Assumptions

Every weight, threshold, and classification rule in
`phase5_scoring_config.py` is explicitly labeled provisional — not
clinically validated, not statistically calibrated. Specifically:
`DIRECTION_FACTORS`/`CONSISTENCY_FACTORS`'s seven-bucket mapping;
`APPLICABILITY_FACTORS`'s four-value mapping and the `min()` aggregation
rule; the five-level tier precedence and which `row_hierarchy_points()`
label maps to which tier; the quality-weighted-mean formula for
`Plant_Applicability_Factor`; the `Scientific_Evidence_Score` range
(`-6..30`). All are internally consistent with the approved architecture
and were exercised, not merely asserted, but none should be presented to
an end user as a clinically validated instrument without further review.

---

## 7. Deferred Risks (unchanged from the addendum, not touched this pass)

- `NO_GO_SAFETY` remains structurally unreachable in the live pipeline
  (scope is always `UNKNOWN`) — Eligibility Gate behavior was NOT
  redesigned in this phase, per explicit instruction.
  `eligible_for_normal_ranking=False` still always blocks normal ranking
  and a Strong decision, verified unchanged.
- Seven of the nine originally-requested applicability dimensions
  (plant part, dose, route, population, duration, and the
  `extraction_or_solvent` variant used by the separate Task 10.2 system)
  still have no persisted column in the real `evidence_records` schema —
  `evaluate_applicability()` will correctly resolve them to
  `NOT_APPLICABLE`/`UNKNOWN` for any real production row until that
  schema work happens; this phase did not add columns or run a
  migration, per instruction.
- `_STRONG_SCORE_THRESHOLD` (`candidate_shortlisting.py`) and
  `_decision_class()`'s `score >= 78` (raw engine) remain two
  independently-defined `78` literals, confirmed identical today but not
  linked by a shared constant (main audit §6, unchanged).
- Legacy callers relying purely on free-text indication signals (no
  `Indication_Match_Type`) will see `Plant_Applicability_Factor` capped
  at `0.60` for the `indication` dimension — an intended consequence of
  "missing data does not receive full credit," but worth flagging to any
  team still using the pre-`general_indication_relevance.py` pathway.

---

## 8. Test Results

See `PHASE5_TEST_RESULTS.md` for the full breakdown.

```
Phase 5 addendum tests:  51 passed, 0 failed, 0 xfailed, 0 skipped
Phase 1-4 tests:        273 passed, 0 failed, 3 xfailed (pre-existing)
Full suite:             2509 passed, 0 failed, 3 xfailed, 0 collection errors
```

No production code was patched to force a test to pass artificially.
Every desired-behavior test passes because the real, traceable
architecture described in §2 now produces the value the test asserts —
verified by hand-computation against the fixtures before this report was
written (see the companion addendum's Round 7 verification table for the
worked numbers each fixture is checked against).

---

## 9. Supervisory correction pass after the first implementation ZIP

Independent review found four behaviors that the original 46 tests did not
cover. They are corrected here and locked by five additional regression
tests:

1. **Primary-tier Evidence Quality:** adding six positive Tier-B animal
   records to one positive A2 RCT no longer changes
   `Evidence_Quality_Score`, `Scientific_Evidence_Score`, or
   `Overall_Score`; only supporting/all-tier diagnostic fields change.
2. **Primary-tier decision profile:** adding negative Tier-B records to a
   positive A2 programme no longer changes its `Go` call. The all-tier
   outcome label remains visible separately for audit.
3. **Unreported denominator:** `2 positive + 8 unreported` now classifies
   `MIXED`; one unreported record is `MIXED`; zero records are
   `INSUFFICIENT`; two positive records are `CONSISTENT_POSITIVE`.
4. **Complete score provenance:** market-only and safety-only rows that
   change their respective published components are present under those
   keys in `Component_Source_Record_IDs` and in the complete authoritative
   union, but not under `Scientific Evidence`.

### Reproduced before/after checks

| Scenario | Before correction | After correction |
|---|---|---|
| 1 positive A2 RCT vs. same RCT + 6 positive Tier-B animal records | `Evidence_Quality_Score` 18.3 → 23.0; `Scientific_Evidence_Score` 12.44 → 15.64; `Overall_Score` 59.8 → 71.8 | Both cases: 18.3 / 12.44 / 59.8; supporting count alone changes 0 → 6 |
| 7 positive A2 RCTs vs. same programme + 5 negative Tier-B animal records | Decision changed `Go` → `Investigate` through the all-tier outcome label | Both remain `Go`, `Overall_Score=82.7`; all-tier diagnostic alone becomes mixed |
| `2 positive + 8 unreported` | `CONSISTENT_POSITIVE` | `MIXED` |
| RCT + market-only + safety-only rows | non-empirical contributors absent from authoritative source union | market/safety IDs are mapped to their components and included in the union, never in `Scientific Evidence` |

### Independent execution environment note

The sandbox used for this correction does not provide the real `streamlit`
or `supabase` distributions and cannot download them from its package index.
Phase-5 tests run directly without either dependency. Phase 1–4 and the full
suite were additionally executed with minimal **test-only stubs located
outside the project tree** (`/mnt/data/test_stubs`) solely to satisfy imports;
the stubs are not included in the deliverable ZIP and no project file imports
them explicitly. Results were 273 passed / 3 pre-existing xfailed and 2509
passed / 3 pre-existing xfailed respectively. A deployment environment with
the real pinned dependencies should rerun the same suite before release.

The implementation is ready for supervisory re-verification; this report does
not claim deployment approval.
