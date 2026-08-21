# Stage 2 — Study Linkage / Evidence Dependency Report

## Scope
Stage 2 was limited to dependency-aware evidence aggregation. It did not redesign the pipeline, alter safety/regulatory gates, change scoring weights, change the six-class decision vocabulary, rewrite Gold Corpus architecture, or modify historical validation artifacts.

## Verified root cause
The existing `deduplication_engine.py` correctly separates article identity from evidence/claim identity. However, `evidence_body_assessment.py` based RCT starting certainty on the raw number of governing records (`len(top)`). As a result, a ClinicalTrials.gov record and a PubMed publication for the same registered trial could be counted as two independent pieces of clinical evidence.

A controlled reproduction with fully characterized RCT records showed:

- one RCT representation: LOW starting/body certainty;
- registry + publication of the same NCT: MODERATE before remediation when methodological coverage was complete.

This was duplicate inflation at the evidence-body dependency layer, not a failure of article-level deduplication.

## Implementation

### `deduplication_engine.py`
Added two additive identity concepts:

- `compute_source_record_identity(record)` — identity of the concrete evidence/source record;
- `compute_study_identity(record)` — identity of the underlying dependency unit.

Rules are deliberately conservative:

1. Direct trial evidence with the same structured ClinicalTrials.gov registration is linked to the same study identity.
2. Primary and secondary publications remain distinct article/evidence objects while sharing the same study identity when they carry the same structured trial registration.
3. Records without structured linkage fall back to source/article identity; no relationship is guessed from free text.
4. Systematic reviews and meta-analyses remain distinct synthesis evidence objects even if a trial registration field is present.

### `evidence_body_assessment.py`
Added `governing_study_count` as an additive, defaulted field on `EvidenceBodyAssessment`.

- `governing_source_count` continues to report the number of governing evidence records, preserving existing semantics.
- `governing_study_count` reports distinct underlying study/dependency units.
- RCT and synthesis multiplicity rules used for starting certainty now use `governing_study_count`, preventing a single registered trial from becoming stronger merely because it appears through multiple records.

No evidence object is deleted by this change.

### `pubmed_connector.py`
PubMed XML parsing now preserves a structured ClinicalTrials.gov accession from `DataBankList` as `NCT_ID` when PubMed supplies it. This enables legitimate linkage between a publication and its registry record without title/text inference.

### Engine version
`DECISION_ENGINE_VERSION` was increased from `1.10.1` to `1.10.2` because evidence-body certainty can affect downstream final scientific decisions.

## Focused Stage 2 scenarios
The new regression tests cover:

1. registry + primary PMID publication = distinct source records, same underlying study;
2. primary publication + secondary analysis = distinct publications, related/dependent study evidence when the same structured NCT is present;
3. two unrelated RCTs = separate studies;
4. systematic review remains a distinct synthesis evidence object;
5. certainty cannot increase merely because one trial is represented twice;
6. two genuinely independent registered RCTs can still increase the independent-study count;
7. PubMed structured ClinicalTrials.gov accession extraction.

## Test results

Focused and broader executable regression suite:

- 148 passed
- 0 failed

The suite covered Stage 2 linkage, evidence-body assessment, connector identifiers, canonical scientific assertions, structured certainty, GRADE-informed certainty, structured final-decision authority, scientific reliability invariants, core reliability regression gates, pharmaceutical safety, regulatory authorization/barriers, and Decision Holdout v2-v5 regression tests.

`python -m py_compile` passed for every changed Python file.

Direct version verification confirmed `DECISION_ENGINE_VERSION == "1.10.2"`.

### Environment-limited suite
`test_phase2_evidence_architecture.py` was also executed. Result:

- 65 passed
- 31 could not execute successfully because importing `database.py` requires the unavailable `supabase` package (`ModuleNotFoundError: No module named 'supabase'`).

The 31 failures share that environment dependency. They are not reported as passing and were not treated as evidence of Stage 2 success.

## Scientific interpretation
Stage 2 improves internal dependency handling. It does **not** establish external scientific validity and does not prove that every publication-to-trial relationship in the repository is known. Linkage remains intentionally conservative: where a structured trial registration is unavailable, the platform does not fabricate study identity.

## Delivery correction — version guard synchronization

A CI run after applying the original Stage 2 delivery exposed two stale version-guard assertions in `test_task16_plant_profile_regulatory_integrity.py` and `test_task17_plant_profile_evidence_freshness.py`. Both still expected engine version `1.10.1` after the Stage 2 bump to `1.10.2`.

This was a delivery/version-tracking omission, not a study-linkage regression. The two assertions were updated to `1.10.2`; no scientific or production behavior was changed. Focused verification: **52 passed, 0 failed** across those two files. A full local suite remains environment-limited by unavailable `supabase` and `streamlit` packages; the user's GitHub Actions environment had otherwise reached **3109 passed, 3 xfailed, 2 failed**, with the only two failures being these stale version assertions.

