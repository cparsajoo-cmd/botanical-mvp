# Phase 4 — Eligibility Gate Redesign — Replacement File Manifest

## Base project

```
botanical-mvp-main (91).zip
```

All files in this package are the final, cumulative Phase 4 version of the
corresponding file in that base project — i.e. every audit round, design
review, correction round, and 2nd-pass correction round applied in
sequence, collapsed into one final version per file. Where a file was
touched in multiple rounds, only its LAST version is included here.

## Extraction / replacement instruction

```
Extract this ZIP into the project root and overwrite files with identical
paths. Every path inside this ZIP matches its real location in the base
project exactly (e.g. benchmark_cases/smoke_cases.json stays under
benchmark_cases/). No file in this package needs to be moved or renamed
after extraction.
```

## Scope confirmation

```
This ZIP contains only complete files created or modified during Phase 4.
It does not contain the full project.
```

29 files total: 4 CREATED, 25 MODIFIED. Nothing else from the base project
is included — extracting this ZIP into a full project checkout only
touches these 29 paths.

## Complete file list

### Core engine / gate logic

```
Path: eligibility_gate.py
Status: CREATED
Purpose: New, self-contained module holding the Phase 4 Eligibility Gate
model (EligibilityStatus, ScoreValidity, FindingScope, DataCompleteness,
RegulatoryDataStatus, SafetySeverity, ContextRelevance, RankingPartition)
and the pure decision function evaluate_eligibility(), plus the
classify_safety_finding()/classify_regulatory_finding() constructors that
turn today's real engine signals into structured findings. Kept separate
from data_contracts.py to avoid coupling a general-purpose contract file
to one engine's internal decision logic (see the module's own docstring
for the full reasoning).

Path: botanical_rd_candidate_engine.py
Status: MODIFIED
Purpose: _decision_class() rewritten to derive its output from
eligibility_gate.evaluate_eligibility() instead of the pre-Phase-4
same_plant bypass (which made GateStatus.NOT_EVALUABLE behave as a silent
pass). _evaluate_gates() gained a 5th "eligibility" key so Gate_Results
can never disagree with Decision_Class. 18 new OUTPUT_COLUMNS
(Eligibility_Status, Hard_No_Go, Eligible_For_Normal_Ranking,
Ranking_Partition, Score_Validity, Gate_Type, Gate_Reason,
Gate_Evidence_IDs, Safety_Gate_Evidence_IDs, Regulatory_Gate_Evidence_IDs,
Safety_Severity, Safety_Scope, Safety_Context_Relevance,
Regulatory_Status, Regulatory_Scope, Regulatory_Context_Relevance,
Data_Completeness, Requires_Expert_Review), inserted before
Decision_Engine_Version (bumped 1.0.3 -> 1.1.0). Added
evidence_records_index (per-EvidenceRecord id/text pairs) to
_build_evidence_text_index() and a 4th return value to
_collect_raw_evidence(), so Safety_Gate_Evidence_IDs /
Regulatory_Gate_Evidence_IDs can be finding-specific (only the specific
EvidenceRecord(s) whose own text contains the matched hit term/barrier
phrase, not the whole row's pooled evidence id list). Added the shared,
independently-testable sort_by_ranking_partition_then_score() function;
run()'s final row order is now Ranking_Partition first, raw score second
— a hard no-go's raw score can no longer place it ahead of a NORMAL-
partition row in the DataFrame's own order, while the DataFrame remains
audit-complete (no row dropped).

Path: candidate_shortlisting.py
Status: MODIFIED
Purpose: _hard_stop() now reads the structured Eligible_For_Normal_Ranking
/ Eligibility_Status fields first (falls back to the old text-regex check
only for a row with neither field at all, e.g. a genuinely pre-Phase-4
record).

Path: step_rd_candidates.py
Status: MODIFIED
Purpose: _recommendation_block()'s legacy and modern fallback branches
both now filter through a real _eligible_mask() / _no_go_mask() instead
of an unguarded head(5) or best-effort regex, closing the audit-proven
"no-go can appear in Recommended" gap in both branches.

Path: pharma_report_generator.py
Status: MODIFIED
Purpose: generate_pharma_report()'s "Top Candidates" section is now
eligibility-filtered (fail-closed default when no eligibility columns
exist at all). New "Excluded — Safety/Regulatory No-Go", "Pending —
Incomplete/Expert Review Required", and "Legacy / eligibility not
evaluated" subsections keep every candidate traceable without letting any
of them into the ranked write-ups.

Path: candidate_output_adapter.py
Status: MODIFIED
Purpose: validate_row() now maps all Eligibility Gate fields (including
Ranking_Partition) onto CandidateAssessment, with explicit fail-closed
defaults ("incomplete" / False / "preliminary_or_expert_review") for any
row missing them — never silently "eligible"/"normal".

Path: data_contracts.py
Status: MODIFIED
Purpose: CandidateAssessment gained 16 new Optional fields mirroring the
Eligibility Gate output (eligibility_status, hard_no_go,
eligible_for_normal_ranking, score_validity, gate_type, gate_reason,
gate_evidence_ids, safety_severity, safety_scope,
safety_context_relevance, eligibility_regulatory_status,
regulatory_scope, regulatory_context_relevance, data_completeness,
requires_expert_review, ranking_partition). No existing field changed.

Path: decision_class_ah.py
Status: MODIFIED
Purpose: classify_decision_ah() now maps the new "Expert review
required..."/"Incomplete —..." Decision_Class strings to
"G — Hold / insufficient evidence" explicitly, so a high-confidence,
high-score EXPERT_REVIEW_REQUIRED/INCOMPLETE row can never fall through
to a Decision_Class_AH letter that go_investigate_hold_no_go() maps to
"Go"/"Investigate".

Path: indication_candidate_discovery.py
Status: MODIFIED
Purpose: This module's own row-construction path (the "indication"
discovery mode, reachable in production via step_evidence.py ->
app.py) initializes every OUTPUT_COLUMNS field to "" — without an
explicit fix, the new Eligible_For_Normal_Ranking column would read as
False for every row from this path, silently hiding genuinely eligible
candidates from Recommended. Added compatibility fields derived from
this module's own existing call/safety_findings signals (its own
hard-safety-exclusion logic, which is NOT itself rebuilt or wired to the
Eligibility Gate — that remains explicitly out of scope for Phase 4).

### Test / fixture files

```
Path: test_eligibility_gate_unit.py
Status: CREATED
Purpose: Pure unit tests of eligibility_gate.py's model/decision table in
isolation, no engine or Streamlit dependency.

Path: test_phase4_eligibility_gate_characterization.py
Status: CREATED
Purpose: Characterization tests recording pre-Phase-4 behavior (proven via
direct execution during the audit). 3 of the original 10 tests are marked
@pytest.mark.phase4_legacy_behavior + xfail(strict=True) because Phase 4
intentionally removed the exact unsafe behavior they assert (the
same_plant Decision_Class bypass and the UI legacy-fallback bug); the
other 7 (including direct tests of the still-existing, now-legacy-only
_hard_safety_gate()/_hard_regulatory_gate() functions) are unchanged and
still pass.

Path: test_phase4_eligibility_gate_desired_behavior.py
Status: CREATED
Purpose: Integration tests against the real, wired production path —
covers same_plant bypass removal, Decision_Class/Eligibility_Status
consistency, Decision_Class_AH never mapping EXPERT_REVIEW_REQUIRED/
INCOMPLETE to a Go class, shortlist/UI/report exclusion of no-go
candidates (both legacy and modern paths), historical-row defaults,
CSV audit-export traceability, the honest "differing plant part still
resolves to EXPERT_REVIEW_REQUIRED, not a fabricated PASS or NO_GO"
contract, explicit no-go(score=99) vs eligible(score=60) ranking
separation across three real consumers, end-to-end finding-specific
Safety_Gate_Evidence_IDs/Regulatory_Gate_Evidence_IDs proofs (via a real
engine.run() with two real EvidenceRecords), and the
Ranking_Partition-before-score sort guarantee (both as a direct unit
test of the shared sort function and end-to-end through run()).

Path: test_gate_layer.py
Status: MODIFIED
Purpose: REQUIRED_GATE_NAMES extended to REQUIRED_GATE_NAMES_WITH_ELIGIBILITY
for the new "eligibility" Gate_Results key; nested-keys test exempts
"eligibility"'s status (a richer EligibilityStatus string, not a
GateStatus enum instance) from the GateStatus isinstance check;
Decision_Class exact-string locks updated for rows with zero evidence
text (now "Incomplete —...") and for different-plant hard-term/
prohibition scenarios without a confirmed scope (now "Expert review
required —..."); OUTPUT_COLUMNS/result.columns count locks bumped
59 -> 74 -> 76 -> 77 across the phase's rounds, each documented inline.

Path: test_task5_sensitivity_analysis_activation.py
Status: MODIFIED
Purpose: Same OUTPUT_COLUMNS count lock bump (59 -> 74 -> 76 -> 77) as
test_gate_layer.py, documented inline.

Path: test_scoring_config.py
Status: MODIFIED
Purpose: Decision_Class exact-string lock updated for a zero-evidence-text
fixture (now "Incomplete —..."); the underlying R&D_Opportunity_Score
values are asserted UNCHANGED (proving the scoring arithmetic itself was
not touched).

Path: test_occurrence_seed.py
Status: MODIFIED
Purpose: Same Decision_Class string update as test_scoring_config.py, same
zero-evidence-text fixture, same score-unchanged guarantee.

Path: test_recommendation_block_phase3.py
Status: MODIFIED
Purpose: Shared _report_ready_row() fixture helper now derives
Eligibility_Status/Eligible_For_Normal_Ranking from the same
Go/Investigate/Hold/No-Go `call` value these tests already parametrize on,
so _recommendation_block()'s new eligibility filtering doesn't
incorrectly exclude these pre-existing fixtures' Go/Investigate rows.

Path: test_phase3_no_plant_disappears.py
Status: MODIFIED
Purpose: Shared row-fixture helper given explicit eligible defaults for
the same reason as test_recommendation_block_phase3.py.

Path: test_phase3_authority_quality_integration.py
Status: MODIFIED
Purpose: Direct _build_evidence_text_index()/_collect_raw_evidence() call
sites updated to unpack the new 5th/4th return values
(evidence_records_index / contributing_records) added for
finding-specific evidence ID traceability.

Path: test_task10_2_preparation_applicability.py
Status: MODIFIED
Purpose: Same _build_evidence_text_index() 5-tuple unpacking update as
test_phase3_authority_quality_integration.py.

Path: test_pharma_report_generator.py
Status: MODIFIED
Purpose: Shared _make_row() fixture helper given explicit
Eligibility_Status="eligible"/Eligible_For_Normal_Ranking=True defaults so
this file's ~67 pre-existing tests (unrelated to eligibility) keep
producing rows that appear in "Top Candidates" as they already assert,
under the new fail-closed default for rows with no eligibility data.

Path: test_task15_decision_engine_version_tracking.py
Status: MODIFIED
Purpose: DECISION_ENGINE_VERSION literal-value assertion updated
1.0.3 -> 1.1.0 (Phase 4 changes Decision_Class/gate outcomes, which is
exactly what this constant's own bump policy requires).

Path: test_task16_plant_profile_regulatory_integrity.py
Status: MODIFIED
Purpose: Same DECISION_ENGINE_VERSION literal-value update as
test_task15_decision_engine_version_tracking.py.

Path: test_task17_plant_profile_evidence_freshness.py
Status: MODIFIED
Purpose: Same DECISION_ENGINE_VERSION literal-value update as
test_task15_decision_engine_version_tracking.py.

Path: test_benchmark_harness.py
Status: MODIFIED (via benchmark_cases/smoke_cases.json fixture change)
Purpose: No code change in this file itself; included because its
assertions read benchmark_cases/smoke_cases.json, which changed (see
below) — re-verified green as part of the same fixture update.

Path: test_botanical_rd_candidate_engine.py
Status: MODIFIED
Purpose: Re-verified/adjusted alongside the eligibility_gate wiring; part
of the same policy-correction ripple as test_gate_layer.py (same_plant
Decision_Class expectations).

Path: test_gold_case_execution.py
Status: MODIFIED
Purpose: Re-verified/adjusted alongside the eligibility_gate wiring; part
of the same policy-correction ripple.

Path: test_phase3_report_shortlist_consistency.py
Status: MODIFIED
Purpose: Re-verified/adjusted alongside the eligibility_gate wiring; part
of the same policy-correction ripple.

Path: benchmark_cases/smoke_cases.json
Status: MODIFIED
Purpose: 3 of 4 gold-style smoke cases' expected decision_class updated
from "Low priority / insufficient data" to "Incomplete — insufficient
safety/regulatory evidence for a validated recommendation" for the
specific pairs that have zero evidence text (the 4th case,
smoke_direct_evidence_present, has real evidence text and is
unchanged — correctly still "Low priority / insufficient data"). Each
updated case's "note" field documents the change inline. gate_status and
decision_class_ah expectations in this fixture are unchanged.
```

## Test results (raw output)

```
$ pytest --collect-only -q
2461 tests collected in 1.93s

$ pytest -q
2458 passed, 3 xfailed, 3 warnings in 57.69s

$ pytest test_phase4_eligibility_gate_desired_behavior.py -q
18 passed in 1.44s

$ pytest test_eligibility_gate_unit.py -q
14 passed in 0.07s

$ pytest test_phase4_eligibility_gate_characterization.py -q
7 passed, 3 xfailed, 3 warnings in 0.99s
```

2458 passed + 3 xfailed = 2461, matching the collected count exactly. Zero
failed tests. The 3 warnings are `PytestUnknownMarkWarning` for the custom
`phase4_legacy_behavior` marker (cosmetic only — no `pytest.ini`/
`pyproject.toml` marker registration exists in this project to attach it
to; does not affect pass/fail).

## Files intentionally NOT changed in Phase 4

Confirmed unchanged, verified by diff against the base project
(`botanical-mvp-main (91).zip`):

- Opportunity Score weights (no change to any scoring formula/weight
  constant in `botanical_rd_candidate_engine.py`'s `_score_candidate()`
  or `ScoringConfig`)
- `global_candidate_ranking_engine.py` — untouched; its own weak Safety/
  Regulatory scoring is unchanged (confirmed out of scope: it only ever
  feeds seed/candidate-pool selection, never the final displayed ranking
  — see the Phase 4 audit)
- Market Engine (`ai_opportunity_engine.py`, `white_space_discovery_engine.py`,
  `investment_decision_engine.py`, `rd_discovery_engine.py`,
  `step_ranking.py`) — untouched; confirmed unreachable from the live
  Streamlit app (`app.py` + `pages/*.py`) by the Phase 4 audit
- Gold Case / `ReferenceClaim` subsystem (`reference_precedence.py`,
  `severity_assignment_policy.py`, `assertion_vocabulary.py`,
  `reference_claim.py`, `gold_case*.py`, etc.) — untouched; confirmed
  disconnected from the live production scoring path by the Phase 4 audit
- Connectors (`multi_source_collector.py`, `supabase_client.py`, etc.) —
  untouched
- Database schema — untouched; no migration included or required by any
  change in this package
- `regulatory_barrier_classifier.py` — untouched; its content
  classification logic was explicitly left alone per the design review
  (a text classifier cannot itself distinguish "checked, nothing found"
  from "never checked" — that signal is supplied by the caller via
  `has_evidence_text`, not derived inside the classifier)

## Remaining limitations (honest, not resolved by Phase 4)

- Contextual-relevance extraction (plant part / preparation / dose /
  route / population / constituent matching between a documented risk
  and a specific candidate row) is still **PARTIAL**: the data model
  (`FindingScope`, `ContextRelevance`) fully supports it, but no live
  production code path extracts these fields today. Every live call to
  `classify_safety_finding()`/`classify_regulatory_finding()` gets
  `scope=UNKNOWN`, `relevance=UNKNOWN` regardless of `same_plant`.
- Because scope/relevance are always `UNKNOWN` in production today, any
  severe safety finding or regulatory prohibition resolves to
  `EXPERT_REVIEW_REQUIRED`, not an automatic `NO_GO_SAFETY`/
  `NO_GO_REGULATORY` — this is intentional (unconfirmed context must
  never silently resolve to a hard exclusion), but it does mean
  `NO_GO_SAFETY`/`NO_GO_REGULATORY` are effectively unreachable through
  today's live text-classification path alone; they require an explicit
  `confirmed_scope`/`confirmed_context_relevance` input a future,
  structured-data-aware caller would supply.
- Missing-data provenance still does **not** distinguish
  `NO_EVIDENCE_FOUND` / `SEARCH_NOT_PERFORMED` / `SOURCE_UNAVAILABLE` —
  only a single two-valued `DataCompleteness`
  (`COMPLETE`/`INCOMPLETE`)/`RegulatoryDataStatus.INSUFFICIENT_DATA`
  signal exists, because the ingestion-layer provenance
  (`multi_source_collector.py`'s per-source error list) does not
  currently propagate into the evidence text the Eligibility Gate sees.
  This was an explicit, documented decision (a fabricated 3-way split
  with no real data behind it would be worse than an honest 2-value
  signal), not an oversight.
- `indication_candidate_discovery.py`'s own hard-safety-exclusion logic
  (`safety_findings`, its own `decision`/`call` construction) is not
  itself rebuilt on the Eligibility Gate model — only made
  schema-compatible with it. A future phase would need to wire this
  module's own safety logic through `eligibility_gate.py` for full
  consistency.

## Per-file SHA-256 checksums

```
benchmark_cases/smoke_cases.json  939c9f1fcf7464e64377b11076af6be9940547b9c65df781cd65a270195aff49
botanical_rd_candidate_engine.py  33bb068925fce6839a60708b62eeb739e5d5dccf2d67cbb2734abc3fce7a1634
candidate_output_adapter.py  6ca2bcb86f8d37c0644891dda66b39fb045821a3cdf7dbe2e0d1dc62238c1d7a
candidate_shortlisting.py  c5eab82d83966c871e78c599de94c62b7656d29532a09ba756c0c088b171975c
data_contracts.py  909600b2cda31e81d1dd289aebfe8aa1fd530bdced9b5c3ba3136a0a54237cd8
decision_class_ah.py  8c3cca9e54ccd1d5c23a30f2cda1c068dfb0842ea9c7b26e64a3ca30fddc74c0
eligibility_gate.py  b02463608b9be648e4db4689847e5c39894b6268b91a45d984410f4cce81dfda
indication_candidate_discovery.py  79f182eb860f30c2601700dce878e0fafb68a8fc2ba6ee7ae1a0eb1f6865167e
pharma_report_generator.py  c8fa7f0ffb7e7c647f54ef03e4768f184dd2ee29befb5e551cb8f1ef132877fb
step_rd_candidates.py  98fa03c8d76173a4068b25d657fe5e06f8aa27ef409d3bbaac0bb1c06010e8f6
test_benchmark_harness.py  93f0dadf1fe0d2725f098636ecb5ec20605278aaa4232fffefb7165f0d6d1350
test_botanical_rd_candidate_engine.py  fb2c30b12acbcba0ef6f44fcfdc453787275b3792cccd0408059ff0e144fd9a5
test_eligibility_gate_unit.py  0e47a4d4e05854f175273481436245a9ef5470aa38573d8b3dcff64c51af4678
test_gate_layer.py  4e4239305e0e70069965544c62ddb3c96c40e39a882a8166f3360b1f6a984cf5
test_gold_case_execution.py  3cff5630738883cef16fce00a712eb1f7db9aef2b1b65e5e99d0c38ecf3a0e86
test_occurrence_seed.py  96de5c9141da7cff3517b660b9e53919d3ca5a6393f48338d2f2518ea536394b
test_pharma_report_generator.py  b7e7f9c0004bd5da9e084dbf838bac24aeaae7deb215f9d0b3764e15ef12a74a
test_phase3_authority_quality_integration.py  b3799a1fc22581471049fa7d2289701364d1e181ebdcc17caa3d533a69d5c6ed
test_phase3_no_plant_disappears.py  1b4a4c01dd2ee326294aa6da44276ec73003a01756e4eb0663fbcebaa09a5529
test_phase3_report_shortlist_consistency.py  b2bcce2567753128b8bf9d7cf419385036b3d7266634b1a5107243d89f0f69af
test_phase4_eligibility_gate_characterization.py  d87ed0127eab3a22a771d71123fc007671e43258635c8b31e21e6b77e128ce37
test_phase4_eligibility_gate_desired_behavior.py  dfb6df51e16842a83afbfd76cb7a1f94f7f7ce0657e62de4f53a1df6df82526d
test_recommendation_block_phase3.py  0c67a21f79ac4620b6ac2da363e95a9f59bccba8b8e30720e9c10598969e675a
test_scoring_config.py  56ade04f6ffb7c18bf933e88e8202b41b43d26e5de7ad70edf1d9f484337c28b
test_task10_2_preparation_applicability.py  41e575d1edcec846c84a3caebdbdf42b1d97930322aea7b40eae8a4a2f31cf03
test_task15_decision_engine_version_tracking.py  afe6fc055b3542b434fc07740317340491853fbad8aa333d85b57ee288e142ed
test_task16_plant_profile_regulatory_integrity.py  05e83769695921fa03d02aa5c6aa26626d33327f50b6c90d14ef08e299bd5996
test_task17_plant_profile_evidence_freshness.py  254f6a7fc26d0068660fcdede30dd0e9d95dd6449c6f9f237585bed7a8dc9728
test_task5_sensitivity_analysis_activation.py  2b9c6c90af5766280758dafb1491f76bf2c24e64dea84a1954c558910c30dd75
```

(Checksums are of the files as staged in this manifest's own build step,
immediately before ZIP creation — they will match the extracted files'
checksums exactly, since ZIP compression does not alter file content.)
