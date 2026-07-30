# Repository Structure — Botanical R&D Decision Intelligence Platform

Snapshot facts: 290 total files, 268 `.py` files, 83 `test_*.py` files, 6 pre-existing `.md` files (before this documentation pass), no `.git` directory (this is a flat snapshot, not a live git checkout), no `README.md` anywhere in the repository.

---

## 1. Directory Tree (top level)

```
.
├── .devcontainer/              Codespaces/devcontainer config (Python 3.11 image)
├── .github/
│   ├── workflows/
│   │   ├── archive-legacy.yml  Current, validated legacy-file archival workflow
│   │   └── tests.yml           CI test workflow
│   └── legacy-files.txt        65 files confirmed unreachable from production (see Section 6 note)
├── benchmark_cases/
│   └── smoke_cases.json        Synthetic mechanics/regression fixtures (NOT Gold Cases)
├── locales/                    en.json, fa.json, fr.json — i18n strings
├── pages/                      Independent Streamlit pages (see Section 3)
│   └── pages/
│       └── Diagnostic.py       Nested duplicate/second copy — see Section 8 note
├── synthetic_validation_fixtures/
│   ├── __init__.py
│   └── fixtures.py             Synthetic (non-Reference-Grounded) validation fixtures
├── app.py                      Main Streamlit entry point (Steps 0–6)
├── ARCHITECTURE.md             Verified, detailed architecture document (pre-existing)
├── VALIDATION_PROTOCOL.md      Reference-Grounded Validation protocol, v0.3 DRAFT (pre-existing)
├── TECHNICAL_DEBT.md           Deferred-issue log, 1 entry (pre-existing)
├── VALIDATION_CASE_TEMPLATE.md Case-authoring template for the ValidationCaseProtocol track (pre-existing)
├── Prospective_Claim_to_Decision_Mapping_Proposal.md  Design doc, adopted into Protocol §14 (pre-existing)
├── case_006_source_suitability_screening.md           Case 006's pre-build screening record (pre-existing)
├── [~230 other .py files]      Engines, connectors, steps, gold cases, data contracts, tests
├── PROJECT_STATUS.md           NEW — this documentation pass
├── DECISIONS.md                NEW — this documentation pass
├── NEXT_ACTIONS.md             NEW — this documentation pass
├── BENCHMARK_PROGRESS.md       NEW — this documentation pass
├── ARCHITECTURE_OVERVIEW.md    NEW — this documentation pass
├── REPOSITORY_STRUCTURE.md     NEW — this documentation pass (this file)
└── CHANGELOG.md                NEW — this documentation pass
```

## 2. Purpose of Each Major Folder

- **`.devcontainer/`** — Codespaces development environment config; installs `requirements.txt` + `streamlit` on container start. Not part of the running application.
- **`.github/workflows/`** — CI: `tests.yml` (test suite) and `archive-legacy.yml` (legacy-file archival, not yet triggered — see `PROJECT_STATUS.md` §16/`NEXT_ACTIONS.md` NA-002).
- **`benchmark_cases/`** — Synthetic smoke-test cases for `benchmark_harness.py`. See `BENCHMARK_PROGRESS.md` Appendix for why these are kept separate from Gold Cases.
- **`locales/`** — Translated UI strings for the Streamlit app (English, Farsi, French).
- **`pages/`** — Streamlit's auto-discovered multi-page mechanism. Each file here is an independently-loaded page, not part of `app.py`'s Step 0–6 flow.
- **`synthetic_validation_fixtures/`** — Fixtures for `GoldCaseKind.SYNTHETIC` cases (pipeline-mechanics testing), distinct from the Reference-Grounded (`GoldCaseKind.REFERENCE_GROUNDED`) cases at repository root.

## 3. Purpose of Each Major Module (by category)

**Streamlit entry points:**
`app.py` (main flow) and `pages/*.py` (`Bulk evidence.py`, `Diagnostic.py`, `Plant_Profile.py`, `Source_Ingestion.py`).

**Step modules** (`step_*.py`, 19 files) — implement individual UI steps. Not every `step_*.py` file is part of the live `app.py`→`pages/` import chain (`ARCHITECTURE.md`'s import-reachability analysis is the authoritative source for which are live vs. legacy — see `.github/legacy-files.txt`).

**The central engine:** `botanical_rd_candidate_engine.py` (237 KB) — `BotanicalRDCandidateEngine`, the one production scoring/decision engine. `botanical_rd_engine.py` is a separate, much smaller (204-byte) file — its relationship to the main engine was not independently re-verified in this pass; do not assume it is a duplicate or a stub without checking.

**Connectors** (`*_connector.py`, 18 files) — one per external data source: ChEBI, ChEMBL, ClinicalTrials.gov, CrossRef, DailyMed, EMA regulatory, EuropePMC, FDA, GBIF, Kew, LiverTox, OpenAlex, OpenFDA, patents, PubChem, PubMed, generic regulatory (legacy stub), Semantic Scholar.

**Evidence pipeline:** `evidence_collector.py`, `evidence_retriever.py`, `evidence_extractor.py`, `evidence_classifier.py`, `evidence_hierarchy_classifier.py`, `evidence_confidence.py`, `evidence_coverage.py`, `evidence_database.py`, `evidence_filtering_engine.py`, `evidence_quality_engine.py`, `evidence_standardizer.py`, `negative_evidence_classifier.py`.

**Gold Case / validation pipeline** (repository root, not a subfolder):
- Core model: `gold_case.py`, `gold_case_execution.py`, `gold_case_persistence.py`, `gold_case_serialization.py`.
- Ground-truth support: `reference_claim.py` *(referenced by gold case files — presence/exact filename not independently re-verified in this pass)*, `reference_descriptor.py` *(same caveat)*, `reference_precedence.py`, `resolved_expected_outcome.py`, `assertion_vocabulary.py`, `applicability_check.py`, `validation_unit.py`.
- Six Gold Case files: `gold_case_reference_grounded_00{1,3,4,5,6,7}_*.py` (no 002).
- Engine-evidence-run files: `case_003_engine_evidence_run.py`, `case_006_engine_evidence_run.py`.
- Agreement/evaluation: `agreement_eligibility.py`, `evaluation_run.py`, `evaluation_run_persistence.py`, `dataset_split.py`.
- The separate ExpertPanel track (out of current protocol scope): `validation_case_protocol.py`, `user_roles.py`, `expert_sign_off.py`, `validation_matrix.py`, `validation_protocol_execution.py`, `validation_protocol_persistence.py`, `validation_unit.py`.

**Decision/scoring support:** `decision_engine.py` *(per `ARCHITECTURE.md`: the old, removed-from-the-live-path duplicate scoring system, kept in the repository but not read by anything downstream)*, `decision_class_ah.py`, `decision_record_persistence.py`, `execution_readiness.py`.

**Post-processing/analysis (never mutate scores):** `scoring_sensitivity_report.py`, `structured_rationale.py`, `comparative_rationale.py`.

**Observability/telemetry:** `connector_session_observability.py`, `telemetry_persistence.py`.

**Reporting:** `pharma_report_generator.py`, `candidate_output_adapter.py`, `data_contracts.py`.

**Data/infrastructure:** `database.py`, `database_builder.py`, `supabase_client.py`, `supabase_data.py`, `schema.py` *(local SQLite, still imported — see `ARCHITECTURE.md` "Known oddities")*.

**Repository integrity tooling:** `repo_dependency_audit.py` — recomputes production/test/legacy classification fresh on every run; the tool that closed the legacy-file-archival gap described in `DECISIONS.md` D-011.

## 4. Important Entry Points

- **Application:** `app.py` (`streamlit run app.py`, per convention — not independently verified as the exact run command in this pass, but consistent with `ARCHITECTURE.md`'s description of Streamlit auto-loading it).
- **Test suite:** `pytest -q` from repository root (no `tests/` subdirectory — all `test_*.py` files sit at repository root alongside the modules they test).
- **Repository integrity check:** `python3 repo_dependency_audit.py summary` / `python3 repo_dependency_audit.py validate . .github/legacy-files.txt`.
- **Gold Case execution (example):** `python3 case_003_engine_evidence_run.py` — has a `if __name__ == "__main__":` block that prints a full execution trace.

## 5. Testing Structure

- 83 `test_*.py` files, all at repository root (no dedicated `tests/` directory).
- 1462 tests collected via `pytest --collect-only` in this documentation-pass environment; 6 test files failed to collect in this environment specifically because of two **missing optional dependencies** (`streamlit`, `supabase`) — not because of any code defect. Affected files: `test_evidence_database_deduplication.py`, `test_multi_source_collector.py`, `test_task10_2_preparation_applicability.py`, `test_task11_1_scientific_evidence_activation.py`, `test_task6_pilot_scope.py`, `test_validation_matrix.py`. Whether these pass in an environment with those dependencies installed was **not verified in this pass**.
- Full test-suite pass/fail status (`pytest -q` executed to completion) was **not run to completion in this documentation pass** — collection only. Do not state elsewhere in this documentation set that "the full suite passes" as a currently-verified fact; `ARCHITECTURE.md` states it passed as of its own last verification, which is a different point in time.
- `test_production_dependency_integrity.py` — the pytest-enforced legacy-file/production-dependency check described in `DECISIONS.md` D-011.

## 6. Validation Structure

Covered fully in `ARCHITECTURE_OVERVIEW.md` §2 and `VALIDATION_PROTOCOL.md`. Two tracks exist side by side: the active `GoldCase` track (repository root, no subfolder) and the out-of-scope `ValidationCaseProtocol`/`ExpertPanel` track (also repository root, no subfolder — both tracks are flat files, not separated into directories).

**Discrepancy noted, not resolved, in this pass:** `ARCHITECTURE.md`'s prose states 66 legacy files were confirmed for archival; `.github/legacy-files.txt` (and its identical root-level copy, `legacy-files.txt`) contains exactly 65 lines in this snapshot. A second, older-looking file, `legacy-files (github folder version).txt`, contains a different (smaller, unreconciled) list referencing "67 files" in its accompanying old workflow copy (`archive-legacy.yml` at repository root, which differs meaningfully from the current `.github/workflows/archive-legacy.yml` — the root copy predates the validation-step fix described in `ARCHITECTURE.md` and `DECISIONS.md` D-011). This suggests the root-level `archive-legacy.yml` and `legacy-files (github folder version).txt` are stale, superseded copies left in the repository root, with `.github/workflows/archive-legacy.yml` and `.github/legacy-files.txt` being the current, authoritative versions — but this was not confirmed with the repository's own author in this pass, so it is recorded here as an observation, not acted upon. See `NEXT_ACTIONS.md` NA-003.

## 7. Documentation Structure

**Pre-existing, in scope (per this pass's task instructions — reviewed, not rewritten):**
- `ARCHITECTURE.md` — verified architecture reference.
- `VALIDATION_PROTOCOL.md` — validation rules, DRAFT v0.3.
- `TECHNICAL_DEBT.md` — deferred-issue log.
- `VALIDATION_CASE_TEMPLATE.md` — case-authoring template (ValidationCaseProtocol track).
- `Prospective_Claim_to_Decision_Mapping_Proposal.md` — adopted design proposal (now Protocol §14).
- `case_006_source_suitability_screening.md` — Case 006's pre-build screening record.

**New, created in this pass:**
`PROJECT_STATUS.md`, `DECISIONS.md`, `NEXT_ACTIONS.md`, `BENCHMARK_PROGRESS.md`, `ARCHITECTURE_OVERVIEW.md`, `REPOSITORY_STRUCTURE.md`, `CHANGELOG.md`.

**Not markdown, but documentation-adjacent:**
`Botanical_Evidence_Database_Professional_Template-1.xlsx`, `Botanical_Platform_Data_Model_v3.xlsx` (data-model spreadsheets — contents not read in this pass; XLSX parsing was out of scope for a markdown documentation task).

## 8. Other Notes Worth Recording

- **`pages/pages/Diagnostic.py`** — a `Diagnostic.py` file exists both directly under `pages/` and under a nested `pages/pages/` subdirectory. Whether this is a real nested-page mechanism Streamlit intentionally supports, a duplication artifact, or something else was **not independently investigated in this pass** — flagged here so it isn't silently missed, not resolved.
- **`case_006_gold_case_file_diff_since_last_handoff.txt`** — a diff/handoff artifact for Case 006; contents not read in full in this pass.
- No `README.md` exists anywhere in the repository, despite `.devcontainer/devcontainer.json` referencing one (`"openFiles": ["README.md", "app.py"]`) as a file VS Code/Codespaces should open automatically. This mismatch was not corrected in this pass, per the instruction not to modify production/config files unless necessary for documentation consistency — flagged here for awareness only.
