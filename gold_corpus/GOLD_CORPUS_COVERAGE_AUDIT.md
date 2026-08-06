# Gold Corpus Scientific Coverage Audit — Phase 7

**Date:** 2026-08-06  
**Scope:** Uploaded repository `botanical-mvp-main (95).zip`  
**Constraint:** corpus-only work; no production logic, scoring, safety/regulatory rules, market logic, or plant-specific engine tuning changed.

## Executive finding

The repository contains **17 active canonical reference-grounded Gold Cases** (Case 002 is abandoned). The active corpus already spans all five `ReferenceDomain` values, but it is not yet a scientifically complete End-to-End holdout corpus because it previously had no per-case `GoldSourceSet` annotations and no independently captured frozen retrieval snapshots.

This pass therefore does **not** add synthetic cases. It converts the 17 existing real cases into a machine-readable Gold Corpus manifest with one mandatory **critical source** per case and supplies `GoldSourceSet` objects that make a missed critical source an explicit End-to-End validation failure.

## Active cases by domain

| Domain | Cases | Count |
|---|---|---:|
| Indication/Evidence | 001, 003, 004, 005, 009, 010, 011, 012 | 8 |
| Preparation specification | 007, 008, 015 | 3 |
| Safety | 006, 014 | 2 |
| Identity/Quality | 013, 017 | 2 |
| Regulatory status | 016, 018 | 2 |
| **Total** |  | **17** |

## Governing/critical source coverage

| Source family | Cases | Coverage |
|---|---|---|
| EMA/HMPC | 001, 006, 007, 008, 009, 010, 012, 014, 015 | 9 |
| Systematic review | 003, 004, 005, 011 | 4 |
| Meta-analysis | 003, 011 (systematic review + meta-analysis) | 2 |
| National regulator | 016, 018 (UK MHRA) | 2 |
| FDA | — | GAP |
| WHO monograph | — | GAP |
| ESCOP monograph | — | GAP |
| Pharmacopoeia as governing source | — | GAP |
| Taxonomic authority | 013, 017 (Kew POWO) | 2 |
| Individual RCT as governing source | — | intentionally unsupported by current INDICATION_EVIDENCE precedence hierarchy |
| Observational study as governing source | — | intentionally unsupported by current INDICATION_EVIDENCE precedence hierarchy |

## Scientific-feature coverage matrix

| Requested stratum | Status | Gold cases / note |
|---|---|---|
| EMA/HMPC | COVERED | 9 cases |
| WHO | GAP | no verified WHO-governed case in uploaded corpus |
| ESCOP | GAP | no verified ESCOP-governed case in uploaded corpus |
| FDA or National Regulators | PARTIAL/COVERED | National regulator: 016, 018; FDA absent |
| Systematic Reviews | COVERED | 003, 004, 005, 011 |
| Meta-analysis | COVERED | 003, 011 |
| RCT | GAP as independently labelled Gold source | pooled RCT evidence appears inside reviews, but no independently curated RCT GoldSourceExpectation |
| Observational Studies | GAP | none independently curated |
| Botanical Identity | COVERED | 013, 017 |
| Safety | COVERED | 006, 014 |
| Contraindications | COVERED | 006 |
| Drug Interactions | COVERED | 006, 014 |
| Dose-specific Evidence | COVERED (regulatory) | 018, dose thresholds 600 mg / 1800 mg |
| Preparation-specific Evidence | COVERED | 007, 008, 015 |
| Regulatory Restrictions | COVERED | 018 |
| Regulatory Prohibition | COVERED | 016 |
| Positive Human Evidence | COVERED | 009, 010, 011, 012; 001 is positive monograph indication |
| Negative Human Evidence | COVERED | 004 |
| Null Human Evidence | PARTIAL | null outcomes occur inside 004/005 reviews, but no standalone null-RCT Gold source |
| Conflicting Evidence | PARTIAL | Case 005 documents Sadahiro 2023 conflict; Case 004 documents older competing review; conflict is not represented as two applicable resolved references |
| Missing Evidence | COVERED semantically | 005 = `AssertionState.INSUFFICIENT`; not the same as retrieval-empty |
| Source Unavailable | FRAMEWORK-ONLY | End-to-End code/tests support it; no real locked corpus source-unavailable case yet |
| Known Irrelevant Sources | GAP | no independently adjudicated real irrelevant-source set |
| Known Duplicate Sources | GAP | no independently adjudicated real duplicate-source set |

## Key architectural limitation discovered

`end_to_end_validation.LiveMultiSourceRetriever` uses a returned `Evidence_Record_ID`, DOI, PMID, NCT ID, URL, or generated live ID as `RetrievedEvidence.reference_id`. Existing Gold Cases use curated internal reference IDs such as `EMA_HMPC_196745_2012_...`. Therefore **live retrieval critical-source matching is not guaranteed to work by exact `reference_id` equality** for every source. This is a benchmark-readiness limitation, not an engine defect, and production logic was not changed in this phase.

Frozen-snapshot runs can use the curated IDs deterministically. Before a scientifically interpretable LIVE benchmark is claimed, canonical source-identifier reconciliation must be handled at the corpus/retrieval-adapter boundary without adding plant-specific rules.

## Corpus changes in this phase

1. Added `gold_corpus/gold_corpus_manifest.json` containing all 17 active cases and the requested scientific fields.
2. Added one verified governing source as **critical** for every active case.
3. Added `gold_corpus/gold_source_sets.py`, producing `GoldSourceSet` objects for all 17 cases.
4. A missing critical source now fails through the already-existing `CRITICAL_SOURCE_MISSED` path; no engine rule was changed.
5. Added known documented competing/supporting reviews to the manifest for Cases 003, 004 and 005, but did **not** promote them to E2E critical/supporting source expectations without independent retrieval records.
6. Updated `BENCHMARK_PROGRESS.md` to include Case 018 and the correct total of 17 active cases.
7. Added corpus integrity tests.

## Why no new Gold Case was added in this pass

The remaining high-value source gaps are WHO, ESCOP, FDA, independently labelled RCTs and observational studies. The uploaded repository does not contain independently verified source records sufficient to construct new cases for those strata. External source search was attempted during this pass but the search service was unavailable. Under the explicit no-fabrication rule, **zero new Gold Cases were added** rather than inventing or weakly sourcing them.

Also, current `reference_precedence.py` does not permit `RCT` or `OBSERVATIONAL_STUDY` as governing source types for `INDICATION_EVIDENCE`. Those study designs should therefore enter the End-to-End Gold Corpus as supporting/critical retrieval sources beneath a valid governing reference, not by changing production precedence or forcing an invalid Gold Case.

## Critical-source policy

Every active corpus entry now has at least one `critical_sources[]` item. The critical ID is the selected governing reference from the existing resolved Ground Truth. In End-to-End evaluation, omission of that ID produces `CRITICAL_SOURCE_MISSED`. Serious-safety and regulatory-prohibition cases also retain the stricter zero-tolerance gate semantics already implemented in Phase 7.

## What remains before scientific End-to-End validation

- Independently capture frozen raw connector snapshots for the corpus (do not derive snapshots from Gold truth text).
- Curate canonical retrieval identifiers (DOI/PMID/document URL/document ID) for critical-source matching.
- Add verified WHO and ESCOP source strata when actual source text is available.
- Add independently labelled individual RCT positive, negative and null sources as retrieval expectations under appropriate Gold Cases.
- Add observational-study retrieval expectations.
- Adjudicate real irrelevant and duplicate sources for retrieval precision.
- Build at least one genuine multi-reference conflict/HUMAN_REVIEW_REQUIRED case only when two actually applicable, same-rank, contradictory references are independently verified.
- Add external expert reviewer provenance and then create an untouched locked holdout split.

No claim of external or clinical validation is made by this audit.

## Test results for this corpus pass

- `pytest -q gold_corpus/test_gold_corpus_manifest.py test_phase7_end_to_end_validation.py` → **30 passed**.
- `pytest -q gold_cases/test_case_*.py gold_corpus/test_gold_corpus_manifest.py test_phase7_end_to_end_validation.py` → **135 passed**.
- Full repository collection cannot complete in this sandbox because `supabase` and `streamlit` are unavailable; 12 test modules fail during collection for those missing third-party dependencies.
- With those 12 dependency-bound modules excluded, the broad suite result is **2441 passed, 3 xfailed, 1 failed**. The one failure is the pre-existing order-dependent `test_production_dependency_integrity.py::test_app_py_and_direct_production_modules_are_import_resolvable` (`ValueError: not enough values to unpack`), already documented by the repository's Phase-7 audit as reproducible in the untouched baseline and unrelated to Gold Corpus changes.

## Final phase summary

1. **Final active Gold Cases:** 17 (001, 003–018; 002 abandoned).
2. **Coverage Matrix:** documented above and machine-readable in `gold_corpus_manifest.json`.
3. **Domains covered:** all five `ReferenceDomain` values.
4. **Major remaining scientific strata:** WHO, ESCOP, FDA-specific representation, independently labelled RCTs, observational studies, standalone null-RCT, genuine applicable same-rank conflict, real source-unavailable holdout, and adjudicated irrelevant/duplicate retrieval labels.
5. **New Gold Cases added:** 0 — deliberately, because no additional source for the remaining gaps was independently verifiable in this pass.
6. **Primary references used:** 9 EMA/HMPC, 4 systematic reviews (including 2 systematic review/meta-analysis cases), 2 Kew POWO taxonomic records, 2 UK MHRA national-regulatory sources.
7. **Files changed/added:** `BENCHMARK_PROGRESS.md`; new `gold_corpus/__init__.py`, `build_gold_corpus_manifest.py`, `gold_corpus_manifest.json`, `gold_source_sets.py`, `test_gold_corpus_manifest.py`, and this audit report.
8. **New tests:** 6 corpus-integrity/E2E-critical-source tests.
9. **Test result:** 30/30 focused Phase-7+Corpus; 135/135 GoldCase+Phase7+Corpus; broad dependency-limited result above.
10. **Scientific-validation limitations:** no independently captured frozen connector snapshots, no untouched locked holdout, no external expert adjudication, and remaining source/study-design strata listed above. Therefore no external/clinical validation claim is made.
