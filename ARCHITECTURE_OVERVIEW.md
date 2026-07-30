# Architecture Overview — Botanical R&D Decision Intelligence Platform

This is a **high-level summary**, not a replacement for `ARCHITECTURE.md` (519 lines, verified by the repository's own automated import-reachability analysis, `repo_dependency_audit.py`). Where this document and `ARCHITECTURE.md` ever disagree, `ARCHITECTURE.md` — and ultimately the code itself — is authoritative. This document exists to orient a new contributor quickly; read `ARCHITECTURE.md` in full before making any architectural change.

Two structurally separate systems share this repository. They are connected only at one point: both read from and reason about the same production engine, `BotanicalRDCandidateEngine`.

---

## 1. The Production Platform (Engine Pipeline)

**Entry points — the only two ways code in this repository actually runs in production:**
- `app.py` — the main Streamlit entry point, running Steps 0–6 in sequence.
- Every file under `pages/` — independently-loaded Streamlit pages (`Bulk evidence.py`, `Diagnostic.py`, `Plant_Profile.py`, `Source_Ingestion.py`), not part of the Step 0–6 flow.

**Pipeline, one stage per step:**

| Step | Responsibility | Key modules |
|---|---|---|
| 0 | Indication / dosage form / market input (fixed selectboxes; free-text can pre-fill them) | `step_inputs.py`, `free_text_question_parser.py`, `question_understanding_engine.py`, `regulatory_frameworks.py` |
| 1 | Question understanding + analysis (keyword/phrase matching against seed vocabularies, not a trained NLU model) | `step_question.py`, `ai_discovery_engine.py`, `seed_data.py` |
| 2 | Live evidence collection, per candidate plant, saved to Supabase (`evidence_records`) | `step_evidence.py`, `research_engine.py`, `multi_source_collector.py`, per-source connectors |
| 3–6 | Market landscape, existing knowledge, R&D discovery, final recommendation — one file implements all four UI steps deliberately (shared cached engine instance/session state) | `step_rd_candidates.py` → `botanical_rd_candidate_engine.py` |
| (optional) | Manual data import | `step_import_data.py`, `supabase_client.py` |

**The one central decision engine:** `BotanicalRDCandidateEngine` (`botanical_rd_candidate_engine.py`, 237 KB — the largest file in the repository). Instantiated in two places (Step 2, for candidate-plant selection only; Step 5, for the actual scoring/decision output the user sees), but there is only one implementation of the scoring/decision logic itself.

**Responsibilities and relationships between major modules** (see `ARCHITECTURE.md` for the full, verified import graph):
- Evidence classification/quality: `evidence_hierarchy_classifier.py`, `negative_evidence_classifier.py`, `evidence_confidence.py`, `concentration_normalizer.py`.
- Decision/scoring: `decision_class_ah.py`, `_score_candidate()` inside the engine.
- Regulatory intelligence: `ema_regulatory_connector.py`, `regulatory_connector.py` (legacy stub, disabled).
- Post-processing/analysis (never mutates scores): `scoring_sensitivity_report.py` (robustness/fragility), `structured_rationale.py` (evidence conflict & consistency, Sprint 4).
- Observability: `connector_session_observability.py` (in-memory, session-scoped), `telemetry_persistence.py` (persistent, best-effort, never fatal).
- Evidence & explainability pipeline (Tasks 10–13): `evidence_records` (Supabase, authoritative) → `standard_evidence_builder.py` → `BotanicalRDCandidateEngine._summarize_applicability()` → `decision_record_persistence.py` → `pharma_report_generator.py`.

**Known, documented architectural facts worth remembering:**
- A local SQLite layer (`schema.py`/`botanical_platform.db`) is still in the active import chain via `seed_data.py`, alongside Supabase (the actual production store) — a known, not-yet-removed oddity.
- Retail product search is a stub (`_search_retail_products()` returns `"Not implemented"`); patent search only activates with `EPO_OPS_KEY`/`EPO_OPS_SECRET` set.
- `pages/Bulk evidence.py` is a separate, manually-triggered page, not part of the automatic Step 0–6 flow.
- `pharma_report_generator.py` has zero import-level dependency on the engine, the database module, or `standard_evidence_builder.py` — verified by AST inspection of its own imports, not just convention.

## 2. The Validation Program (Gold Case / Validation Pipeline)

Governed by `VALIDATION_PROTOCOL.md` (v0.3, DRAFT pending confirmation). Exists to test whether the **existing, unmodified** production engine's decisions agree with real, authoritative reference sources — never to change the engine itself.

**Pipeline, one stage per line:**

```
Real authoritative source (EMA/HMPC monograph, systematic review, etc.)
  → ReferenceClaim extraction (source_locator, evidence_text, VERBATIM/NORMALIZED/TRANSLATED only)
  → reference_precedence.resolve_precedence()  (per-domain source-ranking hierarchy)
  → ResolvedExpectedOutcome  (Ground Truth — GoldCase.resolved_outcomes)

[separately, later, independently-decided per Leakage Rule 9.1:]
Curator-supplied EngineEvidenceInput (frozen, 4-field: scientific_name,
  target_indication, notes, compound_activity_targets)
  → gold_case_execution.execute_gold_case_against_engine()
  → BotanicalRDCandidateEngine.run()  (the SAME production engine — no mock, no parallel path)
  → Decision_Class / Decision_Class_AH / Gate_Results

Ground Truth  +  Engine output
  → agreement_eligibility.assess_agreement_eligibility()  (per Protocol §14)
  → evaluation_run.build_evaluation_run()
  → decision_direction_agreement / safety_serious_false_negative_rate
```

**Structural leakage prevention:** `EngineEvidenceInput` is a frozen, four-field dataclass structurally incapable of holding a `ReferenceClaim` or `ResolvedExpectedOutcome` — the engine can never receive Ground Truth, by type-system construction, not just by procedural discipline. `dataset_split.assess_leakage()` must return `VALID_FOR_HOLDOUT` before a case can be locked or used.

**Per-domain applicability, not one global flag:** a single `ReferenceDescriptor` can be applicable for one domain (e.g., Identity/Quality) and inapplicable for another (e.g., Safety) against the same `ValidationUnit` — `GoldCaseReference.applicability_by_domain` is a dict keyed by domain, not one boolean (`gold_case.py`, "v3 correction #5").

**File-separation convention:** a case's Ground Truth construction file (e.g., `gold_case_reference_grounded_003_matricaria_chamomilla.py`) is kept separate from its engine-evidence/execution file (e.g., `case_003_engine_evidence_run.py`) — enforcing Leakage Rule 9.1's ordering discipline at the file level, not just the process level.

## 3. Benchmark Pipeline

Two, deliberately separate, benchmark-shaped artifacts exist — do not conflate them:

1. **Gold Case benchmark** (the scientific validation program, Section 2 above) — 6 real, reference-grounded cases; full detail in `BENCHMARK_PROGRESS.md`.
2. **`benchmark_cases/smoke_cases.json`** — synthetic, self-described as "NOT a real historical decision, NOT expert-curated," run through `benchmark_harness.py` purely as a mechanics/regression lock on engine code paths (e.g., the hard-safety auto-exclusion path). Not part of the Reference-Grounded Validation program's scientific claims.

## 4. How the Two Systems Meet

The validation program never modifies, mocks, or forks the production engine — `gold_case_execution.execute_gold_case_against_engine()` calls the real `BotanicalRDCandidateEngine`, the same class Step 5 of the production app uses, with curator-supplied `EngineEvidenceInput` standing in for what Step 2's live evidence collection would otherwise produce. This is the entire point of the program: testing the real decision logic, not a stand-in for it.

## 5. Where to Go for More Detail

- Full, verified module-by-module import graph and every architectural decision's rationale: `ARCHITECTURE.md`.
- Validation rules, definitions, and the Prospective Claim-to-Decision Mapping: `VALIDATION_PROTOCOL.md`.
- Directory-level layout and entry points: `REPOSITORY_STRUCTURE.md`.
- Every individually-recorded project decision with reasoning and alternatives: `DECISIONS.md`.
