# PHASE 2 — Evidence Architecture Audit (state BEFORE this phase's changes)

This document describes the Evidence pipeline exactly as it existed before
any Phase 2 code change. It is not rewritten after implementation to hide
what was found — see `PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md` for what was
actually changed and what limitations remain.

## 1. Shapes Evidence travels in today

| Stage | Shape | File |
|---|---|---|
| Connector output | `list[dict]`, PascalCase-ish keys (`PMID`, `DOI`, `NCT_ID`, `Source_Title`, ...) — no shared base class | `pubmed_connector.py`, `europepmc_connector.py`, `openalex_connector.py`, `crossref_connector.py`, `semantic_scholar_connector.py`, `clinicaltrials_connector.py` |
| Allowlist normalization | `dict` built from `STANDARD_FIELDS` (fixed key set) | `source_ingestion_engine.normalize_source_record()` |
| Standardization / LLM enrichment | `dict` (superset of the allowlist, plus hand-copied fields, plus `LLM_*` fields) | `evidence_standardizer.standardize_extracted_record()` |
| Applicability enrichment | same `dict`, plus `Applicability_*` keys and `Direct_For_Selected_Product` | `standard_evidence_builder.build_standard_evidence()` |
| Persistence payload (write) | plain `dict` mapped field-by-field to Supabase column names | `database.save_evidence_record()` |
| Persistence payload (read) | plain `dict` rows, assembled into a `pandas.DataFrame` (`evidence_df`) | `database.load_evidence_records()` |
| Read-time consumption path | `pandas.DataFrame` (deduplicated) | `evidence_database.load_evidence_database()` → `deduplication_engine.deduplicate_evidence()` |
| Scoring / decision input | `pandas.DataFrame` rows read by column name | `botanical_rd_candidate_engine.py` |
| Decision persistence | JSON-serialized `dict` (`applicability_summary`, incl. `evidence_record_ids`) inside `decision_records.records` | `decision_record_persistence.py` |
| Data-contract dataclasses (partial, read-only adapters) | `@dataclass` (`ScientificEvidence`, `RegulatoryRecord`, `EvidenceApplicability`, `EvidenceHierarchyLevel`, `MarketVerificationStatus`) | `data_contracts.py`, built by `standard_evidence_builder.py` |
| GoldCase validation-only input | frozen `@dataclass(frozen=True) EngineEvidenceInput` (4 fields, structurally disconnected from the DB-backed pipeline) | `engine_evidence_input.py` |

There is **no single canonical class** carrying Evidence between connector and
scoring today. Every stage is a loosely-typed dict; field presence/shape is
enforced only by convention and by the allowlist in `source_ingestion_engine.py`.

`STANDARD_EVIDENCE_FIELDS` in `standard_evidence_schema.py` (17 keys) is a
**different, narrower, legacy dict template** — grep shows it is not imported
anywhere else in the repository (`grep -rn "STANDARD_EVIDENCE_FIELDS"` returns
only its own definition). It predates `source_ingestion_engine.STANDARD_FIELDS`
(37 keys) and appears to be superseded/orphaned, not actively used to gate or
shape any record today. `standard_evidence_schema.py` is otherwise the emptiest,
least-committed module with "evidence schema" in its name — which is why it is
the chosen home for the new canonical model (see implementation report).

## 2. End-to-end path

```
connector (list[dict])
  -> evidence_standardizer.standardize_extracted_record()
       -> source_ingestion_engine.normalize_source_record()  [allowlist filter]
       -> hand-copied-back fields (PMID/DOI/NCT_ID/Evidence_Level/... )
       -> optional LLM enrichment (llm_extractor)
       -> standard_evidence_builder.build_standard_evidence()  [applicability + Score fields]
  -> database.save_evidence_record(dict)
       -> sources table (by url/title lookup-or-insert)
       -> plants table (by scientific_name lookup-or-insert)
       -> evidence_records table (insert, with insert-time duplicate check)
  -> database.load_evidence_records() -> pandas.DataFrame (join plants+sources)
  -> evidence_database.load_evidence_database() -> deduplication_engine.deduplicate_evidence(df)  [read-time defensive dedup]
  -> botanical_rd_candidate_engine.py (scoring; builds Applicability_Summary incl. evidence_record_ids)
  -> decision_record_persistence.persist_decision_record()  [JSON snapshot incl. evidence_record_ids]
```

## 3. Sites with structural problems

### 3a. Scattered dict construction
Every connector (`pubmed_connector.py`, `europepmc_connector.py`,
`openalex_connector.py`, `crossref_connector.py`, `semantic_scholar_connector.py`,
`clinicaltrials_connector.py`) constructs its own ad-hoc `dict` with no shared
constructor or validation.

### 3b. Same concept, different names
- `Source_Title` (source_ingestion_engine allowlist) vs. article title
- `Source_Year` vs. publication year
- `NCT_ID` (connector/DB column `nct_id`) vs. "Trial Registration"
- `Study_Type` vs. study design
- `Result_Direction` vs. evidence direction
- `Evidence_Level` vs. evidence quality **and** (separately, in places) study/evidence hierarchy level — Phase 1 deliberately keeps `Study_Type`, `Result_Direction`, and `Evidence_Level` as three independent axes; nothing in Phase 1's code merges them, and this phase does not either (see `evidence_standardizer.py` comments and `data_contracts.EvidenceHierarchyLevel` vs. the plain `Evidence_Level` string field — these are two separate concepts already, not unified).
- `Primary_Outcome` vs. outcome
- `Scientific_Name` vs. plant species
- `Notes` (raw article text / extraction free text) is the closest existing field to "supporting sentence"; there is no separate, shorter "supporting sentence" field anywhere in the schema.

### 3c. Fields dropped by the allowlist and hand-restored later
`source_ingestion_engine.STANDARD_FIELDS` does **not** include: `PMID`, `DOI`,
`NCT_ID`, `Evidence_Level`, `Sample_Size`, `Primary_Outcome`, `Result_Direction`,
`Safety_Signal`, and others. `evidence_standardizer.py` already hand-copies most
of these back in after the allowlist filter runs (see its inline comments,
which document this exact defect for `Evidence_Level` and then again for the
PMID/DOI/NCT_ID group).

**New finding this audit adds:** `Source_Authority_Weight`, `Source_Priority`,
and `Source_Category` — set by `multi_source_collector._save_records_from_connector()`
just before calling `standardize_extracted_record()` — are **not** in the
allowlist and are **not** in the existing hand-restore list either, so they are
silently dropped at `normalize_source_record()` and never reach
`database.save_evidence_record()` or the `evidence_records` table today. This
is the same class of bug already fixed for `Evidence_Level`/`PMID`/`DOI`, just
not previously caught for these three fields.

### 3d. Deduplication
Three independent mechanisms exist, with three independent rules:

1. **Insert-time**, `database.save_evidence_record()` → `_find_existing_source()`
   (matches by `sources.url` first, then `sources.title`) combined with an
   exact-match check on `evidence_records` (`plant_id`, `source_id`,
   `target_indication`, `dosage_form`). This never looks at DOI/PMID/NCT_ID at
   all — those columns exist on `evidence_records` (added in a later,
   undocumented-migration Phase, see §4) but are not part of any dedup key.
   Two connectors returning the same article under different URLs (e.g.
   `doi.org/...` vs `pubmed.ncbi.nlm.nih.gov/...`) are **not** caught here.

2. **Read-time defensive**, `deduplication_engine.deduplicate_evidence()`
   (used by every caller of `evidence_database.py`) — key = `Source_URL` (or
   `Source_Title` or a `Notes` snippet, in that fallback order) + normalized
   plant + indication + dosage form. Keeps the highest
   `Evidence_Score + Evidence_Quality_Score` row. This also never looks at
   DOI/PMID/NCT_ID.

3. **Collector-level**: none. `multi_source_collector.py` saves every
   connector's records independently; nothing there detects that PubMed and
   Europe PMC returned the same article before both get persisted.

These three levels **do not share an identity function** today, and none of
them use DOI/PMID/NCT_ID even though those identifiers are already collected
by several connectors and already have dedicated `evidence_records` columns.

### 3e. Double counting / duplicate scoring
No score-contribution-level deduplication exists anywhere. `score_breakdown_schema.py`
stores `Score_Breakdown` as either a formatted string or a flat
`{component_name: value}` dict — there is no per-evidence-item score
contribution list to deduplicate against; the aggregation into named
components already happens upstream of anything this phase can safely
observe without touching the frozen scoring engine. This audit records that a
same article surfaced twice (once via PubMed, once via Europe PMC, each
independently persisted per §3d.1) would currently produce two separate
`evidence_records` rows, each eligible to independently influence whatever
component aggregates evidence counts/quality — i.e., the double-counting risk
the Phase 2 brief warns about is real today, and stems from §3d (article-level
dedup gaps), not from any score-list-level bug.

## 4. Where DOI / PMID / NCT_ID / DB id / evidence_record_ids / score-to-evidence references already exist

- **DOI**: connector field `DOI` (populated by `europepmc_connector.py`,
  `crossref_connector.py`; **not** populated by `openalex_connector.py` or
  `semantic_scholar_connector.py`, confirmed by grep — both return other
  metadata but no `DOI` key). Persisted column `evidence_records.doi` (added,
  undocumented migration, per the "Phase 2 (IMPLEMENTATION_PLAN.md)" comment
  block at the top of `database.py`; see `migrations/` for what does exist
  on disk). Round-trips through `evidence_standardizer.py`'s hand-restore list.
- **PMID**: connector field `PMID` (`pubmed_connector.py`, `europepmc_connector.py`).
  Persisted column `evidence_records.pmid`.
- **NCT_ID / Trial Registration**: connector field `NCT_ID`
  (`clinicaltrials_connector.py`). Persisted column `evidence_records.nct_id`.
  No connector or column currently uses the words "Trial Registration" — that
  is this brief's requested canonical name only.
- **Evidence record database ID**: `evidence_records.id` (Supabase primary
  key, auto-generated). Read back into the DataFrame as `Evidence_Record_ID`
  (`database.load_evidence_records()`, added for Task 10.2).
- **`evidence_record_ids`**: a list of `Evidence_Record_ID` values, built in
  `botanical_rd_candidate_engine.py` (`Applicability_Summary["evidence_record_ids"]`)
  and `indication_candidate_discovery.py`, persisted verbatim by
  `decision_record_persistence.py`, read by `pharma_report_generator.py` and
  `step_rd_candidates.py`. This is the existing traceability backbone this
  phase must reuse, not replace.
- **Score-to-evidence references**: exist only at the *candidate* level
  (`evidence_record_ids` on `Applicability_Summary`), not at the
  *individual-score-component* level. There is no existing structure mapping
  "this +3.2 in the Evidence Quality component came from evidence_record #482"
  — components are pre-aggregated numbers by the time anything in scope for
  this phase can observe them.

## 5. Deduplication rule conflicts (explicit)

| | Insert-time (`database.py`) | Read-time (`deduplication_engine.py`) |
|---|---|---|
| Identity basis | `sources.url` → `sources.title` fallback, plus exact `plant_id`+`target_indication`+`dosage_form` match | `Source_URL` → `Source_Title` → `Notes` snippet fallback, plus normalized plant+indication+dosage |
| DOI/PMID/NCT_ID used? | No | No |
| Keeps which row on conflict? | First existing row wins (returns its id; nothing new inserted) | Highest `Evidence_Score + Evidence_Quality_Score` wins |
| Article vs. Evidence granularity | Conflates "same article" with "same article for this exact indication+dosage_form" (deliberately, per the plant_id fix comment in `save_evidence_record()`, to avoid dropping genuinely distinct plant/indication contexts) | Same conflation, same granularity |

Both layers, independently, already encode "same source + same
plant/indication/dosage_form = duplicate" — they agree on *shape* of the rule
but use **different literal string-matching logic** (URL/title cleaning
differs slightly) and neither is DOI/PMID/NCT_ID-aware. This is the gap Phase
2 closes with a single shared identity function, reused (not replacing) both
layers, per the phase brief's mandate to keep insert-time vs. read-time as two
call sites of one policy.

## Addendum — review round

The original delivery's audit (sections 1-5 above) is left unedited, per the
brief's own instruction not to rewrite a "before" document to hide what was
found. This addendum records what the review round's re-inspection of the
implementation (not a re-audit of the original pre-Phase-2 codebase) found:

- `canonicalize_evidence_record()` existed but was called nowhere in
  production — confirmed by grep showing zero call sites outside its own
  definition and the original test file. Fixed; see
  PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md section 2.
- `dedupe_score_contributions()` existed but was called nowhere in
  production — same pattern. Fixed; see section 3.
- `compute_evidence_identity()`'s five-field composition could collapse two
  outcomes or two directions from the same article. Fixed; see section 4.
- No fuzzy title matching existed despite being an explicit original
  requirement. Fixed; see section 5.
- Insert-time and read-time dedup policies had diverged again (insert-time
  never got a title/year/author fallback in the original delivery). Fixed;
  see section 6.
- `first_author` had no alias/derivation support and was always None; no
  connector populates it either way (confirmed unchanged in this round).
  Pipeline-side fixed; connector-side explicitly left undone with reasoning
  in section 7.
- `to_legacy_dict()` dropped `first_author`/`preparation`/`dose` on export,
  a round-trip data-loss bug. Fixed; see section 8.
- `to_dict()` did not actually convert non-JSON-native types recursively.
  Fixed; see section 9.
- The original test suite exercised helpers directly but never proved a
  production code path actually invoked them. Fixed with spy-based and
  fake-Supabase-backed integration tests; see section 10.

## Addendum — review round 3

The original delivery's audit and the review-round-2 addendum above are
left unedited. This continues the addendum with what the round-3 review of
the round-2 implementation found:

- `_find_existing_evidence_by_identity()` matched on DOI/PMID/NCT_ID plus
  plant/indication/dosage_form only — it stopped there and treated any
  match as a duplicate, silently collapsing genuinely different Evidence
  (different outcome, direction, population, dose) from the same article.
  Fixed with a genuine two-phase check; see
  PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md section 2. A related bug (article-
  key re-derivation asymmetry between the new record and a DB-sourced
  candidate) was found and fixed during this round's own test-writing, also
  documented there.
- `_fuzzy_collapse_remaining()` (read-time) had the identical problem one
  layer up: it collapsed two rows on `articles_equivalent()` alone, which
  only ever decides article-level equivalence, not evidence-level
  equivalence. Fixed by requiring the new `evidence_contexts_equivalent()`
  helper to also agree; see report section 3.
- The round-2 `score_contributions` structure attached the same evidence
  list to every score component of a candidate. Even with a documented
  caveat next to it, this shape reads as per-component attribution the
  scoring engine does not provide. Replaced with an explicitly
  candidate-level `score_context` structure
  (`attribution_level: "candidate"`, `component_attribution_available:
  False`); see report section 4. This report now states plainly, in one
  place (report section 1), the exact boundary between "duplicate
  prevention before scoring" (done) and "duplicate prevention inside
  scoring" (not done, out of scope).
- The round-2 insert-time fuzzy fallback's "title + year + author" framing
  was not actually author-gated in practice, because `sources` has no
  author column and `articles_equivalent()` silently skipped the author
  check whenever it was unverifiable on one side. Fixed by raising the
  required similarity threshold specifically when author is unverifiable,
  and by correcting the documentation to describe this honestly as a
  title+year check with a raised bar, not a title+year+author check; see
  report section 5.
- The round-2 test suite proved true-positive dedup extensively but had
  comparatively few false-positive (must-NOT-dedupe) tests. A 7-row
  false-positive matrix was added, plus ~20 additional targeted
  false-positive tests across issues 1, 2, and 4; see report sections 2, 3,
  5, and 6.

## Addendum — review round 4

- `database.save_evidence_record()`'s legacy URL/title source-reuse path
  (`_find_existing_source()` followed by a bare
  `source_id + plant_id + target_indication + dosage_form` lookup) was
  still deciding Evidence duplication by itself, with no evidence-context
  comparison at all — the same class of bug already fixed on the DOI/
  PMID/NCT_ID and fuzzy-title paths in round 3, left unfixed on this
  third, older path. Fixed by routing this path through the same
  `_fetch_evidence_identity_candidates()` + `evidence_contexts_equivalent()`
  machinery the other two paths already use — no new, parallel lookup
  logic was introduced. See PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md
  section on round 4 for the exact before/after and the regression test
  that locks this in.

## Addendum — review round 5

- `evidence_records` never had `dose` or `preparation` columns, despite
  `compute_evidence_identity()`/`evidence_contexts_equivalent()` comparing
  both dimensions since round 1 — meaning the database side of every
  identity comparison always saw them as empty, regardless of what a new
  record carried. Since the repository already has an established,
  documented, idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
  migration pattern for exactly this situation (see
  `migrations/0002_extend_evidence_records.sql`), a minimal migration
  (`migrations/0006_add_dose_preparation.sql`) was added following that
  same pattern, rather than overloading an existing JSON column. See
  PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md's round 5 addendum for the full
  before/after.
- **A second, independent, pre-existing bug was found and fixed while
  writing this round's tests:** `_evidence_context_components()`'s
  "preparation" dimension read only the canonical key `"preparation"` via
  `_get_any(row, "preparation")` — missing the `"Preparation"` legacy-key
  alias every OTHER dimension in that function already had (e.g.
  `_get_any(row, "dose", "Dose")`). Since `evidence_contexts_equivalent()`
  and `compute_evidence_identity()` canonicalize a plain input dict via
  `canonicalize_evidence_record()`, which returns a LEGACY-shaped dict
  (`to_legacy_dict()`, i.e. `"Preparation"`, not `"preparation"`), the
  preparation dimension had been silently comparing as `""` on both sides
  for every plain-dict caller since round 1 — meaning "Preparation" never
  actually differentiated two Evidence rows in practice, even before the
  database persistence gap this round's task described. This was caught by
  `test_r5_url_title_same_preparation_different_two_evidence` failing
  during this round's own development, not missed. Fixed by adding the
  missing alias.
