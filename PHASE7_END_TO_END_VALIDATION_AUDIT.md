# Phase 7 — End-to-End Scientific Validation & Benchmarking Audit

Date: 2026-08-06

## 1. Validation framework before Phase 7

The repository already had a reference-grounded validation architecture: `GoldCase`, `ValidationUnit`, `ReferenceDescriptor`, `ReferenceClaim`, resolved outcomes, leakage controls, `EvaluationRun`, persistence, validation protocol execution, and a separate synthetic `benchmark_harness.py` regression lock. `ValidationScope.END_TO_END` already existed in `assertion_vocabulary.py`, but `evaluation_run.EvaluationRun.__post_init__` explicitly rejected it. `PROVIDED_EVIDENCE` therefore tested interpretation/gates/decision translation only; retrieval was explicitly out of scope.

Implemented metrics before this phase were only `decision_direction_agreement` and `safety_serious_false_negative_rate`. Documentation explicitly said gate-level agreement, Top-k inclusion, pairwise agreement, and GRADE calibration were not implemented. No retrieval precision/recall, critical-source recall, classification accuracy, regulatory benchmark metrics, or benchmark-run comparison existed.

## 2. Gold corpus audit

Active registry: 17 reference-grounded cases (Case 2 is abandoned).

Domain coverage:
- Indication/Evidence: 8
- Preparation specification: 3
- Safety: 2
- Identity/Quality: 2
- Regulatory status: 2

Source-type coverage:
- EMA/HMPC: 9
- Systematic review: 4
- Taxonomic authority: 2
- National regulatory: 2

Risk-stratum tags actually present:
- Clean-Baseline: 8
- Interaction: 2
- Safety-Serious: 1
- Safety-Moderate: 1

Important limitation: all 17 active cases currently have `engine_evidence=[]`; they are development cases, not an already-executable locked-holdout END_TO_END corpus. Each active case currently carries one primary reference. Therefore full-corpus retrieval precision, F1/confusion matrices for sparse classes, and a scientifically meaningful END_TO_END baseline cannot honestly be claimed yet.

Underrepresented or absent as explicit independently labelled Gold-source strata: WHO, ESCOP, individual RCT source cases, dose-specific risk, null human RCT, conflicting evidence, missing-evidence benchmark, source-unavailable benchmark, and a fully adjudicated irrelevant/duplicate retrieval corpus.

## 3. Phase 7 implementation

Added `end_to_end_validation.py`, which extends the existing GoldCase truth objects and the already-reserved `ValidationScope.END_TO_END` without changing `PROVIDED_EVIDENCE` behavior.

End-to-end path:

`ValidationQuestion -> candidate_discovery -> retriever -> availability handling -> article-level deduplication -> evidence interpretation/classification checks -> production BotanicalRDCandidateEngine -> safety/regulatory gates -> Decision_Class -> ranking -> metrics/failure attribution`

Evidence is not supplied through `GoldCase.engine_evidence` in the END_TO_END path. The retriever API receives only the question and discovered candidates; it never receives `case_id`, expected outputs, ReferenceClaims, or resolved outcomes.

Two modes are separate:
- `BenchmarkMode.FROZEN_SNAPSHOT`: deterministic CI/regression retrieval over immutable `RetrievedEvidence` snapshots.
- `BenchmarkMode.LIVE_RETRIEVAL`: `LiveMultiSourceRetriever` adapts the repository's existing `multi_source_collector.collect_multi_source_evidence(save=False)` production collector. Connector/import failures become explicit unavailable records and then `SOURCE_UNAVAILABLE`; absence is never converted to clearance.

## 4. Gold Source Set

Implemented `GoldSourceSet` and `GoldSourceExpectation` with roles:
- critical
- supporting
- optional
- irrelevant
- duplicate

Per-source optional truth labels support expected study design, direction, applicability, source authority, evidence quality, safety-critical, regulatory-critical, and duplicate linkage. Metrics are not fabricated when these annotations are missing.

## 5. Retrieval metrics

Implemented:
- `critical_source_recall`
- `evidence_retrieval_recall`
- `evidence_retrieval_precision_labelled_subset`
- `irrelevant_evidence_rate`
- `duplicate_retrieval_rate`

Precision is explicitly labelled as a Gold-labelled subset metric unless a fully adjudicated corpus exists.

## 6. Evidence classification metrics

Implemented, denominator permitting:
- `study_design_accuracy`
- `evidence_direction_accuracy`
- `applicability_classification_accuracy`
- `source_authority_classification_accuracy`
- `evidence_quality_classification_agreement`

The framework deliberately returns NOT_COMPUTABLE for zero-denominator classes instead of inventing values. Per-class precision/recall/F1/confusion matrices are not claimed for the current 17-case corpus because the required labelled class support does not exist yet.

## 7. Safety metrics

Implemented:
- `safety_source_recall`
- `serious_safety_false_negative_rate`
- `safety_gate_sensitivity`
- `safety_gate_specificity`
- `safety_expert_review_rate`

Failure attribution explicitly separates `CRITICAL_SOURCE_MISSED` (retrieval) from `SERIOUS_SAFETY_EVIDENCE_IGNORED` (gate). Serious safety failures are CRITICAL.

## 8. Regulatory metrics

Implemented:
- `regulatory_prohibition_recall`
- `restriction_detection_rate`
- `regulatory_status_agreement` for currently labelled prohibition/restriction Gold cases

Source-unavailable handling is explicit. A retrieved critical regulatory prohibition that does not fail the regulatory gate becomes CRITICAL `REGULATORY_PROHIBITION_IGNORED`.

Conflicting-regulatory-source agreement requires additional adjudicated Gold cases; the framework does not fabricate a conflict metric without them.

## 9. Decision metrics

Implemented:
- `decision_direction_agreement`
- `no_go_recall`
- `unsafe_positive_decision_rate`
- `invalid_strong_recommendation_rate`
- `incomplete_as_validated_error_rate`

Broad decision direction remains Positive / Negative / Hold / Abstain-compatible with the existing `DecisionDirection` vocabulary. Exact Decision_Class range fields are retained on case results for future corpus annotation, but no fake threshold calibration was introduced.

## 10. Ranking metrics

Implemented:
- `top_3_inclusion`
- `top_5_inclusion`
- `gold_candidate_rank`
- `unsafe_candidate_in_top5_rate`

A negative/NO_GO candidate appearing in Top-5 is a CRITICAL `NO_GO_IN_TOP5` failure.

Ranking stability is supported through run-to-run `ranking_changes`; a scalar stability coefficient is not claimed until repeated benchmark snapshots have an agreed design.

## 11. Failure attribution

Implemented stages:
`RETRIEVAL_FAILURE`, `DEDUPLICATION_FAILURE`, `CLASSIFICATION_FAILURE`, `DIRECTION_FAILURE`, `APPLICABILITY_FAILURE`, `SAFETY_GATE_FAILURE`, `REGULATORY_GATE_FAILURE`, `SCORING_FAILURE`, `DECISION_FAILURE`, `RANKING_FAILURE`, `SOURCE_UNAVAILABLE`, `REFERENCE_AMBIGUITY`.

Severity enum: CRITICAL / HIGH / MEDIUM / LOW.

Missing critical evidence is attributed to retrieval, not scoring. Retrieved-but-ignored safety/regulatory evidence is attributed to the corresponding gate.

## 12. Benchmark reproducibility/versioning

`BenchmarkVersions` records benchmark version, Gold corpus version, scoring model version, ruleset version, evidence schema version, and connector versions.

`EndToEndEvaluationRun` records execution timestamp, mode, data snapshot, configuration hash, unique run ID, case results, metrics, failures, and limitations.

`persist_end_to_end_run()` is append-only: one immutable JSON file per run ID; overwrite is refused.

## 13. Regression comparison

`compare_benchmark_runs()` reports:
- metric improved/worsened
- cases fixed/regressed
- new/resolved critical failures
- retrieval changes
- decision changes
- ranking changes

Frozen and Live runs cannot be compared as if they were the same mode.

## 14. Tests added

`test_phase7_end_to_end_validation.py`: 24 tests, all passing.

They cover backward scope separation, question-started retrieval, critical source recall/miss, irrelevant evidence, duplicate counting, positive/negative/null RCT direction, applicability mismatch, safety retrieval miss, source unavailable, regulatory prohibition miss, NO_GO Top-5 violation, incomplete-result handling, decision agreement, Top-3/Top-5, root-cause attribution, version/hash snapshot, regression comparison, deterministic frozen runs, Gold-case-ID leakage prevention, live-retriever unavailable degradation, and append-only persistence.

## 15. Suite result / regression status

Phase-7 test file: **24 passed**.

Broad suite in this sandbox, excluding tests that cannot collect because `supabase`/`streamlit` are unavailable and excluding the known order-dependent production-import integrity test: **2432 passed, 3 xfailed**.

When using the same 12 dependency-related exclusions but retaining the production-import test:
- original uploaded project: **2411 passed, 3 xfailed, 1 failed**
- Phase-7 project before the final two tests were added: **2433 passed, 3 xfailed, 1 failed**

The same aggregate-run failure exists in the untouched original (`test_production_dependency_integrity.py::test_app_py_and_direct_production_modules_are_import_resolvable`, `ValueError: not enough values to unpack`). It passes in isolation and is not caused by Phase 7. The sandbox cannot install the pinned dependencies because its package index has no matching `supabase==2.31.0` distribution.

No production scoring weights, Safety rules, Regulatory rules, Market Engine, UI, or plant-specific behavior were modified.

## 16. Actual baseline metrics

A scientifically interpretable END_TO_END baseline is **not computable from the current 17 active real Gold cases** because:
1. they have no END_TO_END GoldSourceSet annotations yet;
2. they have no frozen connector-output snapshots;
3. all have empty `engine_evidence` and are development rather than an executable locked-holdout E2E set;
4. irrelevant/duplicate corpus labels needed for full retrieval precision are absent.

The correct baseline status for those metrics is therefore NOT_COMPUTABLE, not 0% or 100%. The Phase-7 tests execute the metric machinery and production-engine path as engineering verification only; their fixture outputs are not reported as scientific-validation performance.

## 17. Critical / High failures discovered

Corpus-readiness findings, not engine-performance claims:
- HIGH: no active END_TO_END locked-holdout corpus exists yet.
- HIGH: no frozen retrieval snapshots are attached to the 17 active real Gold cases.
- HIGH: all active Gold cases currently contain zero `engine_evidence`; existing PROVIDED_EVIDENCE EvaluationRun cannot produce a current scientific baseline without a separate evidence curation/loading step.
- HIGH: current source coverage is concentrated in EMA/HMPC and systematic reviews; WHO/ESCOP and individual RCT benchmark representation is absent from the active registry.
- HIGH: full retrieval precision cannot be estimated from the current corpus because known-irrelevant corpus coverage is not adjudicated.

No new CRITICAL production defect was proven by an executed real Gold benchmark in this phase; claiming one without such a run would violate the phase requirements.

## 18. What remains before a real Scientific Validation claim

Curate and lock an independent END_TO_END holdout set with explicit GoldSourceSet labels; capture frozen raw connector snapshots independently from Gold truth; add WHO/ESCOP, RCT positive/negative/null, dose/preparation risks, regulatory conflict, missing/source-unavailable and irrelevant/duplicate retrieval cases; run live retrieval with production dependencies/connectors configured; add external expert adjudication and reviewer provenance; establish preregistered/provisional acceptance thresholds from baseline rather than tuning on Gold cases; and preserve a genuinely untouched holdout for future release decisions.

Until those steps are complete, the correct claim is: **Phase 7 End-to-End validation infrastructure is implemented and regression-tested, but external/scientific validation of platform performance has not yet been demonstrated.**
