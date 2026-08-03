# Project Status — Botanical R&D Decision Intelligence Platform

**This is the project's live dashboard. It should always answer: "Where are we now?"**

Status: created by repository documentation pass. Grounded exclusively in what is verifiable inside this repository snapshot (no `.git` history is present in this snapshot, so anything date-dependent that isn't stated inside a document is marked UNKNOWN).

---

## 1. Project Vision

A decision-intelligence platform for botanical (herbal) R&D candidates: given an indication, dosage form, and target market, it collects scientific/regulatory evidence per candidate plant, scores and gates candidates through `BotanicalRDCandidateEngine`, and produces a ranked, explainable recommendation (`Decision_Class` / `Decision_Class_AH`) — plus a parallel, rigor-focused **Reference-Grounded Validation program** whose job is to check whether that engine's decisions agree with real, authoritative reference sources (EMA/HMPC monographs, systematic reviews, etc.) on individually curated Gold Cases.

Two workstreams share this repository:
1. **The production platform** — Streamlit app (`app.py` + `pages/`), described fully in `ARCHITECTURE.md`.
2. **The validation program** — `GoldCase` / Reference-Grounded Validation v4, described fully in `VALIDATION_PROTOCOL.md`.

## 2. Current Development Phase

- **Production platform:** "Phase 7 (repository cleanup)" per `ARCHITECTURE.md`'s own header — the phase is about consolidating/auditing the codebase (legacy-file archival), not adding new engine capability. Feature-numbered work up through "Sprint 6A.2" (persistent connector telemetry) and "Tasks 10–13" (evidence/explainability pipeline) is documented as complete in `ARCHITECTURE.md`.
- **Validation program:** "Reference-Grounded Validation v4," `VALIDATION_PROTOCOL.md` version **v0.3 (Phase 4 — Evaluation Layer)**, status **DRAFT — pending Hamid's final confirmation of this revision**.

## 3. Current Repository Version

UNKNOWN. No `.git` directory is present in this snapshot (verified — `ls -la .git` finds nothing) and no single repository-wide version file or tag exists. The only explicit, dated version markers found are inside `VALIDATION_PROTOCOL.md`'s Change History (Section 15): v0.1, v0.2, and v0.3 are all dated **2026-07-29**. No corresponding version marker exists for the production-platform side (`ARCHITECTURE.md` labels itself only "Phase 7," no date).

## 4. Overall Project Status

- Production platform: functioning single-pipeline Streamlit app per `ARCHITECTURE.md`, with a documented, not-yet-executed legacy-file archival step (Section 9 below) and several explicitly-acknowledged stubs/gaps (Section 10).
- Validation program: **16 real Reference-Grounded Gold Cases built** (case IDs 001, 003–017 — there is no Case 002; see Section 8), spanning **5 of 5** `ReferenceDomain` values (updated 2026-08-03; this section previously understated the count as 6, which predated Cases 008–017 — see `NEXT_ACTIONS.md` and `BENCHMARK_PROGRESS.md` for full reconciliation detail). Protocol document is in draft pending explicit sign-off.

## 5. Current Priorities

Per the most recent dated material in the repository (`VALIDATION_PROTOCOL.md`'s own "Status of this document" closing note):
- Hamid's final confirmation of `VALIDATION_PROTOCOL.md` v0.3, specifically Sections 3, 6, 10/11, and 14 (the newly adopted Prospective Claim-to-Decision Mapping, especially the still-open `CONDITIONAL` question in 14.2).
- On the platform side: running the not-yet-triggered legacy-file archival workflow (Section 9) is the one explicitly "ready but not done" action documented in `ARCHITECTURE.md`.

No other prioritization ranking (e.g., "next Gold Case," "next Sprint") is stated anywhere in the repository as of this snapshot — anything beyond the two items above is PENDING / not yet decided in-repo.

## 6. Completed Milestones

**Production platform (`ARCHITECTURE.md`):**
- Steps 0–6 consolidated into a single Streamlit flow (`app.py` + `step_*.py`), with `BotanicalRDCandidateEngine` as the one central scoring/decision engine (duplicate parallel scoring system removed in Phase 2).
- Free-text question pre-fill (`free_text_question_parser.py`) and `question_understanding_engine.py` wired into `step_inputs.py`.
- Phase 4: `concentration_normalizer.py`, `evidence_hierarchy_classifier.py`, `negative_evidence_classifier.py`.
- Phase 6: `evidence_confidence.py`, `decision_class_ah.py`.
- Phase A/B (Sprint 5): EMA regulatory-status bug fix (`_ema_listed()`) and Regulatory Intelligence reporting; legacy fabricated regulatory stub disabled (`_LEGACY_STUB_ENABLED = False`), not deleted.
- Sprint 3: `scoring_sensitivity_report.py` (fragility report + robustness analysis), post-processing only.
- Sprint 4: Evidence Conflict & Consistency Intelligence, extending `structured_rationale.py` (`classify_evidence_consistency()`, `build_possible_explanations()`, `detect_research_gaps()`, etc.), verified not to alter scoring (`test_sprint4_addition_does_not_change_scores_or_ranking`).
- Sprint 6A.1: session-scoped connector observability (`connector_session_observability.py`) — in-memory only, no persistence, no network call added.
- Sprint 6A.2: persistent connector telemetry (`telemetry_persistence.py`) — best-effort, never fatal, one row per connector outcome per session.
- Tasks 10–13: Evidence & Explainability Pipeline, from `evidence_records` through `pharma_report_generator.generate_pharma_report()`.
- `repo_dependency_audit.py` + `test_production_dependency_integrity.py` + `archive-legacy.yml`: closes the process gap that previously let a stale legacy-file list silently drift out of sync with actual production imports (documented as the cause of a near-miss where `question_understanding_engine.py` was almost archived while in active production use).

**Validation program (`VALIDATION_PROTOCOL.md` / gold case files):**
- Phase 1: `GoldCase` data model (`gold_case.py`) — per-reference-per-domain applicability (v3 correction #5).
- Phase 2: real-engine execution bridge (`gold_case_execution.py`, `execute_gold_case_against_engine()`), locked via `test_gold_case_execution.py` and `test_structural_leakage_boundary.py`.
- Phase 3 / Phase 4: `agreement_eligibility.py`, `evaluation_run.py` — the Prospective Claim-to-Decision Mapping (adopted into protocol as Section 14, v0.3).
- 16 Reference-Grounded Gold Cases built (see Section 8 / `BENCHMARK_PROGRESS.md` for full detail; reconciled 2026-08-03):
  - Case 001 — Melissa officinalis (Indication/Evidence, sleep)
  - Case 003 — Matricaria chamomilla (Indication/Evidence, sleep) — no Case 002 exists
  - Case 004 — Ginkgo biloba (Indication/Evidence, cognitive impairment)
  - Case 005 — Cimicifuga racemosa (Indication/Evidence, menopausal symptoms)
  - Case 006 — Hypericum perforatum (Safety/Contraindication) — first Safety-domain case
  - Case 007 — Valeriana officinalis (Preparation Spec) — first Preparation-Spec-domain case, ground-truth-only
  - Case 008 — Ginkgo biloba, folium (Preparation Spec) — rebuilt 2026-08-01 from a superseded, non-canonical draft; see `NEXT_ACTIONS.md` for the leftover-file cleanup item
  - Case 009 — Melissa officinalis, folium (Indication/Evidence, mental stress)
  - Case 010 — Passiflora incarnata, herba (Indication/Evidence, mental stress)
  - Case 011 — Matricaria chamomilla (Indication/Evidence, generalized anxiety disorder) — corrected 2026-08-01 from an invalid SAFETY-domain draft
  - Case 012 — Lavandula angustifolia, aetheroleum (Indication/Evidence, sleep)
  - Case 013 — Echinacea purpurea (Identity/Quality) — first Identity/Quality-domain case, governed by Kew Plants of the World Online
  - Case 014 — Ginkgo biloba, folium (Safety/Interaction with dabigatran, severity MODERATE)
  - Case 015 — Hypericum perforatum, herba (Preparation Spec)
  - Case 016 — Piper methysticum (Regulatory Status/Prohibition) — first Regulatory-Status-domain case, governed by UK MHRA
  - Case 017 — Matricaria chamomilla (Identity/Quality) — second Identity/Quality-domain case, governed by Kew Plants of the World Online

  With Cases 013, 016, and 017, **all 5 `ReferenceDomain` values are now covered** (previously only 3 of 5 — Identity/Quality and Regulatory Status were open gaps).

## 7. Remaining Milestones

Explicitly documented as not-yet-done:
- Run the legacy-file archival GitHub Action (`archive-legacy.yml`) and verify `archive/` + `archive/ARCHIVED_FILES.md` afterward (`ARCHITECTURE.md`, Section "Legacy files").
- Hamid's final confirmation of `VALIDATION_PROTOCOL.md` v0.3.
- Resolution of the deliberately-left-open `CONDITIONAL` → `DecisionDirection` mapping policy (Protocol §14.2) — explicitly deferred until more Reference-Grounded cases exist.
- TD-001 batch reassessment, targeted after ~10–15 Gold Cases are completed (currently 6 exist) — see `TECHNICAL_DEBT.md`.
- Any further Gold Cases beyond the 6 documented (no specific next-case plan is recorded in-repo as of this snapshot — see `NEXT_ACTIONS.md`).
- Sprint 6A.2's stated future scope item, "Sprint 6A.3" or equivalent persistent-telemetry aggregation, is **not** referenced anywhere — no such future sprint is named in-repo; do not assume one exists.

## 8. Architecture Status

Fully documented in `ARCHITECTURE.md` (519 lines) — see `ARCHITECTURE_OVERVIEW.md` in this pass for a condensed summary. Key facts:
- Single production entry point: `app.py` (Steps 0–6) plus 4 independent Streamlit pages under `pages/`.
- One central engine: `BotanicalRDCandidateEngine` (`botanical_rd_candidate_engine.py`, 237 KB — the largest file in the repository).
- A local SQLite layer (`schema.py`/`botanical_platform.db`) remains in the active import chain alongside Supabase (the actual production store) — documented as a known oddity, not yet removed.
- Two stubs documented as intentionally incomplete: retail product search (`_search_retail_products()` returns `"Not implemented"`) and patent search (only activates with `EPO_OPS_KEY`/`EPO_OPS_SECRET`).

## 9. Validation Infrastructure Status

- `ValidationScope.PROVIDED_EVIDENCE` only is in scope for the current program; `END_TO_END` retrieval validation is explicitly reserved for a future, not-yet-started phase.
- `GoldCaseKind.REFERENCE_GROUNDED` is the only kind this program produces (as opposed to `GoldCaseKind.SYNTHETIC`, used only by the separate `benchmark_cases/smoke_cases.json` mechanics/regression fixtures — see `BENCHMARK_PROGRESS.md`).
- The `ValidationCaseProtocol`/`ExpertPanel` track exists in the codebase (`validation_case_protocol.py`, `user_roles.py`, `expert_sign_off.py`) but is explicitly out of scope for the current protocol document (Section 3) — the mechanism to compare its output against a live expert panel does not yet exist.
- Leakage control is enforced both structurally (`dataset_split.LeakageControl`/`assess_leakage()`) and procedurally (Protocol §9's mandatory ordering rule) — the prospective-order requirement for `expected_decision_direction` (§14.6) is explicitly **not** programmatically enforced; it is a documented process control only.

## 10. Benchmark Status

See `BENCHMARK_PROGRESS.md` for full detail. Summary:
- 6 Reference-Grounded Gold Cases (case files exist and are populated with real reference claims).
- A separate, smaller set of **synthetic smoke-test cases** exists in `benchmark_cases/smoke_cases.json`, explicitly documented in-file as "NOT a real historical decision, NOT expert-curated" — mechanics/regression locks only, unrelated to the Reference-Grounded Validation program's scientific claims.
- No repository-wide numeric benchmark-size target is stated anywhere. The only related numeric target found is TD-001's "~10–15 cases" threshold for a batch technical-debt review, not a stated final benchmark size.

## 11. Gold Case Statistics

**Reconciled 2026-08-03 — this table previously stopped at Case 007 and understated the program by 10 cases.** Full table, verified directly against each case file's own dataclass fields (not against secondary documents):

| # | Case ID | Taxon | Domain | Assertion Type | Assertion State | Governing Source Type |
|---|---|---|---|---|---|---|
| 001 | `refgrounded_001_melissa_officinalis_sleep` | Melissa officinalis | Indication/Evidence | Supports indication | PRESENT | EMA_HMPC |
| 003 | `refgrounded_003_matricaria_chamomilla_sleep` | Matricaria chamomilla | Indication/Evidence | Supports indication | CONDITIONAL | SYSTEMATIC_REVIEW |
| 004 | `refgrounded_004_ginkgo_biloba_cognitive` | Ginkgo biloba | Indication/Evidence | Supports indication | ABSENT | SYSTEMATIC_REVIEW |
| 005 | `refgrounded_005_cimicifuga_racemosa_menopausal` | Cimicifuga racemosa | Indication/Evidence | Supports indication | INSUFFICIENT | SYSTEMATIC_REVIEW |
| 006 | `refgrounded_006_hypericum_perforatum_safety_interaction` | Hypericum perforatum | Safety | Contraindication | PRESENT | EMA_HMPC |
| 007 | `refgrounded_007_valeriana_officinalis_preparation_spec` | Valeriana officinalis | Preparation Spec | Preparation specification | PRESENT | EMA_HMPC |
| 008 | `refgrounded_008_ginkgo_biloba_preparation_spec` | Ginkgo biloba | Preparation Spec | Preparation specification | PRESENT | EMA_HMPC |
| 009 | `refgrounded_009_melissa_officinalis_mental_stress` | Melissa officinalis | Indication/Evidence | Supports indication | PRESENT | EMA_HMPC |
| 010 | `refgrounded_010_passiflora_incarnata_mental_stress` | Passiflora incarnata | Indication/Evidence | Supports indication | PRESENT | EMA_HMPC |
| 011 | `refgrounded_011_matricaria_chamomilla_indication_evidence` | Matricaria chamomilla | Indication/Evidence | Supports indication | PRESENT | SYSTEMATIC_REVIEW |
| 012 | `refgrounded_012_lavandula_angustifolia_sleep` | Lavandula angustifolia | Indication/Evidence | Supports indication | PRESENT | EMA_HMPC |
| 013 | `refgrounded_013_echinacea_purpurea_identity_quality` | Echinacea purpurea | Identity/Quality | Identity confirmation | PRESENT | TAXONOMIC_AUTHORITY |
| 014 | `refgrounded_014_ginkgo_biloba_safety_interaction` | Ginkgo biloba | Safety | Interaction (severity MODERATE) | PRESENT | EMA_HMPC |
| 015 | `refgrounded_015_hypericum_perforatum_preparation_spec` | Hypericum perforatum | Preparation Spec | Preparation specification | PRESENT | EMA_HMPC |
| 016 | `refgrounded_016_piper_methysticum_regulatory_prohibition` | Piper methysticum | Regulatory Status | Prohibition | PRESENT | NATIONAL_REGULATORY |
| 017 | `refgrounded_017_matricaria_chamomilla_identity_quality` | Matricaria chamomilla | Identity/Quality | Identity confirmation | PRESENT | TAXONOMIC_AUTHORITY |

Rows 001–007 sourced as previously documented (see prior revision in version control). Rows 008–017 verified 2026-08-03 by reading each case file's `_build_claim()`/`_build_reference()` dataclass construction directly (not from `QUALITY_RECORDS_INDEX.json`, which had two stale entries — see that file's own `index_metadata.reconciliation_note` for detail).

- Domains covered: Indication/Evidence (8 cases: 001, 003, 004, 005, 009, 010, 011, 012), Safety (2 cases: 006, 014), Preparation Spec (3 cases: 007, 008, 015), Identity/Quality (2 cases: 013, 017), Regulatory Status (1 case: 016).
- **All 5 `ReferenceDomain` values are now covered** — the Identity/Quality and Regulatory Status gaps recorded here as of the prior revision are closed.
- `AssertionType` values now exercised: `SUPPORTS_INDICATION`, `CONTRAINDICATION`, `PREPARATION_SPECIFICATION`, `INTERACTION`, `IDENTITY_CONFIRMATION`, `PROHIBITION`. Other `AssertionType` values remain untested.
- `AssertionState.NOT_STATED` remains untested (all 16 cases use PRESENT, ABSENT, CONDITIONAL, or INSUFFICIENT).
- Case 006 (SAFETY/CONTRAINDICATION/PRESENT) and Case 014 (SAFETY/INTERACTION/PRESENT/MODERATE) both exist now, so `safety_serious_false_negative_rate` almost certainly has data to compute from — but this was **not independently re-run in this pass**; still PENDING per NA-004 until `evaluation_run.py` is actually executed against the current case set.

## 12. Frozen Gold Cases

Cases 001, 003, 004, 005, and 006 are each described in their own module docstrings as not constructing `EngineEvidenceInput`/execution logic in the same file (a deliberate separation, "Leakage Rule 9.1"), with Case 003 and Case 006 having a documented separate engine-evidence-run file (`case_003_engine_evidence_run.py`, `case_006_engine_evidence_run.py`). Cases 007–017 follow the same separation convention (each declares `EngineEvidenceInput`/`engine_evidence_attached=false` deliberately absent) but none of Cases 007–017 has a separate engine-evidence-run file yet — meaning no whole-case engine execution/agreement has been run for any of them. Whether each case's Ground Truth layer is *formally* "frozen" (e.g., a repository convention, a specific field, or just a documentary convention) is **PENDING/UNKNOWN** — no single `frozen: true`-style flag was found during this pass; case files describe themselves informally as not to be edited (e.g., Case 003's own docstring: "gold_case_reference_grounded_003_matricaria_chamomilla.py is frozen"). A full, verified freeze inventory across all 16 cases was not completed in this documentation pass — see `NEXT_ACTIONS.md`.

## 13. Abandoned Gold Cases

- **Case 002 (Passiflora)** — referenced only in passing, as "Access-Blocked" (`Prospective_Claim_to_Decision_Mapping_Proposal.md`, line 119: "Case 002 (Passiflora, Access-Blocked): unaffected, same reason.") and confirmed absent as a file (`case_006_source_suitability_screening.md`: "note: no Case 002 file exists"). No dedicated record of why it was abandoned (beyond "Access-Blocked") was found in this repository snapshot. This is the only confirmed abandoned/skipped case *number*.
- **Superseded (not abandoned, but not canonical) — Case 008's original draft.** `gold_case_reference_grounded_008_ginkgo_biloba_indicationevidence.py` (domain INDICATION_EVIDENCE, hard-coded per `CASES_008_009_010_012_CORRECTION_REPORT.md`) was replaced 2026-08-01 by `gold_case_reference_grounded_008_ginkgo_biloba_preparation_spec.py` (domain PREPARATION_SPEC). Unlike Case 002, the old file was never deleted and its test (`test_case_008_indicationevidence.py`) still exists at repository root. This is a distinct category from "abandoned" — it is a live, importable, non-canonical file sitting alongside the real Case 008. See NA-010 in `NEXT_ACTIONS.md`.

## 14. Technical Debt Summary

One entry currently recorded in `TECHNICAL_DEBT.md`:

- **TD-001** — Case 004 (Ginkgo biloba)'s `ReferenceDescriptor.preparation`/`.population` fields were sourced from the EMA/HMPC monograph's posology, not independently derived from the governing Cochrane systematic review's own trial data. Does not affect Ground Truth (`assertion_state`/`evidence_text`/`selected_reference_id` are 100% Cochrane-sourced). Explicitly deferred for batch reassessment after ~10–15 Gold Cases exist (currently 6).

`TECHNICAL_DEBT.md`'s own framing: entries here are the explicit alternative to acting on them now, reviewed as a batch, not case-by-case.

## 15. Current Risks

Explicitly documented risks/threats (not fabricated — drawn directly from `VALIDATION_PROTOCOL.md` §13, "Threats to Validity"):
- Selection bias (choosing an easy or edge-case case).
- Extraction bias (a curator's reading of a source is itself interpretive).
- Confirmation leakage (unconsciously shaping engine evidence toward an expected result).
- Construct validity of the metrics — only `decision_direction_agreement` and `safety_serious_false_negative_rate` are implemented; gate-level agreement, top-k inclusion, and GRADE calibration are not.
- Reactivity (building a case specifically to demonstrate the pipeline works could bias case selection).

Repository-level risk (from `ARCHITECTURE.md`): the legacy-file archival list previously went stale once already (near-miss with `question_understanding_engine.py`) — the same class of drift could recur for any future file if `repo_dependency_audit.py` isn't re-run after import-chain changes.

## 16. Pending Work

- Confirmation of `VALIDATION_PROTOCOL.md` v0.3 by Hamid.
- Running the legacy-file archival workflow.
- TD-001 batch reassessment (not due yet — threshold not reached).
- Resolving the `CONDITIONAL` → `DecisionDirection` mapping policy (Protocol §14.2), currently `UNRESOLVED` by deliberate, documented choice.
- Full "freeze status" inventory across all 6 Gold Cases (see Section 12).

## 17. Immediate Next Actions

See `NEXT_ACTIONS.md` for the actionable, prioritized version of this list.

## 18. Long-Term Roadmap

No explicit long-term roadmap document exists in this repository snapshot beyond the phase/sprint/task history already captured in `ARCHITECTURE.md` and the domain-coverage gaps noted in `case_006_source_suitability_screening.md`. Any long-term roadmap beyond what is listed in Sections 7 and 16 is UNKNOWN — do not infer one.

## 19. Last Updated

This document was generated during a repository documentation pass triggered by an explicit request to create a self-documenting project knowledge layer. No prior version of `PROJECT_STATUS.md` existed in the repository. Update this section's date manually when this file is next revised, since no automated timestamping exists in this repository for markdown files.
