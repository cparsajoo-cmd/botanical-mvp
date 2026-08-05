# PHASE 2 — Evidence Architecture Implementation Report

**This report has been updated in place after a third review round that
found 3 critical architectural issues and 1 important issue in the second
delivery. It replaces the second report; it is not a parallel document.**
Section headers below map onto the round-3 issues. Round-1 and round-2
content that is still accurate is kept; content the round-3 review
correctly identified as wrong (mainly the original `score_contributions`
design) has been removed and replaced, not left standing alongside a
correction.

## 0. What changed in round 3, in one paragraph

Round 2 wired a canonical adapter and a score-duplication guard into
production, but two of round 2's own mechanisms had real bugs: insert-time
dedup collapsed genuinely different Evidence (same article, different
outcome/direction/population) into one row, and read-time fuzzy dedup did
the same. Round 3 fixes both by separating "is this the same article"
(`articles_equivalent()`) from "is this the same scientific claim/context"
(`evidence_contexts_equivalent()`, new) and requiring BOTH before two rows
collapse, at both insert-time and read-time. Round 3 also found that round
2's `score_contributions` structure — despite its prose caveats — was a
data shape that implied a per-component evidence attribution the scoring
engine does not actually provide, and replaces it with an explicitly
candidate-level structure that cannot be mistaken for that.

## 1. Duplicate article/evidence prevention vs. duplicate score-contribution prevention — READ THIS FIRST

The review explicitly asked for these two claims to never be blurred
together. Stated as plainly as possible:

**Duplicate article/evidence prevention BEFORE scoring: DONE, at the
database/read-time layer.**
- `database.save_evidence_record()` — two-phase insert-time dedup (see
  section 2).
- `deduplication_engine.deduplicate_evidence()` — read-time dedup, exact-key
  pass then a fuzzy pass that requires both article AND evidence-context
  equivalence (see section 3).
- This happens BEFORE any row reaches `botanical_rd_candidate_engine.py`'s
  scoring — a duplicate that is caught here never has a chance to
  contribute to a score twice, because it is never inserted/never survives
  the read twice in the first place.

**Duplicate score-contribution prevention INSIDE the scoring engine: NOT
DONE. Out of scope for this phase. Stated as a limitation, not a completed
requirement.**
- `botanical_rd_candidate_engine.py` produces pre-aggregated
  `{component: value}` totals with no per-evidence attribution at all —
  confirmed in the Phase 0 audit and unchanged by any round of this phase.
  There is no code path, in this phase or before it, that can point to
  "evidence X contributed Y to component Z."
- `score_breakdown_schema.dedupe_score_contributions()` — the utility built
  in round 1 for exactly this — remains present, unit-tested, and UNUSED in
  production as of this round. It is not imported by
  `decision_record_persistence.py` anymore (round 3 removed that import —
  see section 4). It is kept as ready infrastructure, per the review's own
  instruction, not deleted.
- What IS persisted (`score_context`, see section 4) is honestly labeled
  `"attribution_level": "candidate"` and `"component_attribution_available":
  False` — a reader of the persisted JSON cannot mistake it for
  per-component attribution.

## 2. Insert-time dedup is now genuinely two-phase (issue 1)

`database._find_existing_evidence_by_identity()` (the DOI/PMID/NCT_ID path)
and `database._find_existing_evidence_by_fuzzy_title()` (the no-strong-
identifier fallback) both now run in two phases:

- **Phase 1 — find article candidates.** For the identity path: query
  `evidence_records` for rows sharing the same `plant_id`/
  `target_indication`/`dosage_form` AND the same `doi`/`pmid`/`nct_id`,
  fetching (not just `id`, as round 2 did, but) `population`,
  `primary_outcome`, `result_direction`, `study_type`, `notes`, and
  `plant_part` — the fields needed to actually compare evidence context.
  For the fuzzy path: query `sources` narrowed by year (bounded,
  `limit(200)`, unchanged from round 2), then narrow further via
  `articles_equivalent()`.
- **Phase 2 — confirm evidence context.** A candidate is only treated as a
  duplicate when `deduplication_engine.evidence_contexts_equivalent(new_record,
  candidate_row)` is `True` — comparing species, indication, dosage form,
  preparation, plant part, dose, population, outcome, study design,
  evidence direction, and a claim fingerprint (the exact same dimensions
  `compute_evidence_identity()` uses, but WITHOUT re-deriving or comparing
  article identity — see the bug note below for why that distinction
  matters).

**Bug found and fixed during this round's own testing (disclosed, not
hidden):** the first implementation of phase 2 compared full
`compute_evidence_identity()` strings (which include an article-key
component re-derived from whatever title/DOI/author fields happened to be
present on each side). Since `evidence_records` has no author column, a
candidate's re-derived article key could never include an author — so a new
record with a `first_author` value would spuriously fail to match a true
duplicate purely because of an article-key mismatch, not because the
evidence itself differed. This was caught by
`test_r3_issue1_doi_same_evidence_identity_fully_same_second_insert_skipped`-
style testing during development, not missed. The fix:
`evidence_contexts_equivalent()` compares ONLY the non-article scientific
dimensions — article equivalence was already established in phase 1 by the
exact DOI/PMID/NCT_ID match (or, on the fuzzy path, by
`articles_equivalent()`), so phase 2 does not need to, and must not,
re-derive it.

**On ambiguity, the record is kept, never silently collapsed:**
`_fetch_evidence_identity_candidates()` returns `None` (distinct from an
empty list) whenever a query cannot be resolved (e.g. the `doi`/`pmid`/
`nct_id` column itself doesn't exist on an older deployment), and both
callers treat `None` as "cannot determine, therefore not a duplicate, insert
the record." `plant_part` alone missing degrades to comparing "" on that one
dimension (the other five always-present dimensions still gate the
comparison) rather than aborting the whole check.

**Tests** (`test_r3_issue1_*` in `test_phase2_evidence_architecture.py`,
against a real in-memory fake-Supabase harness, not just the pure identity
functions): DOI same + outcome different → both inserted; DOI same +
direction different → both inserted; PMID same + population different →
both inserted; NCT same + claim same with different formatting → one
record; DOI same + evidence identity fully same → second insert skipped.

## 3. Fuzzy read-time dedup now preserves evidence identity (issue 2)

`deduplication_engine.evidence_contexts_equivalent(a, b)` is new — it
factors the exact same per-dimension comparison `compute_evidence_identity()`
already used (species, indication, dosage form, preparation, plant part,
dose, population, outcome, study design, evidence direction, claim
fingerprint) into a standalone function that does NOT require or compare
article identity at all.

`_fuzzy_collapse_remaining()` (the second dedup pass inside
`deduplicate_evidence()`) now requires **both**:

```
articles_equivalent(a, b) AND evidence_contexts_equivalent(a, b)
```

before collapsing two rows. `articles_equivalent()` alone (fuzzy article
match) is no longer sufficient — exactly the bug the round-3 audit
identified: a fuzzy-matched article with a genuinely different outcome or
direction was being incorrectly collapsed to one row.

**Tests:** fuzzy title + outcome different → both remain; fuzzy title +
direction different → both remain; fuzzy title + population different →
both remain; fuzzy title + claim same with punctuation differences → one
remains; fuzzy title + plant part different → both remain; a full
`deduplicate_evidence()` pass on a two-row DataFrame with fuzzy-matched
titles and distinct outcomes keeps both rows.

## 4. score_contributions replaced with an honest, candidate-level score_context (issue 3)

The round-2 `score_contributions` structure is REMOVED, not merely
re-labeled. It attached the same `evidence_record_ids`/`evidence_identities`
list to every score component, which — regardless of the prose caveat next
to it — is a data shape that reads as "this evidence backed this
component," a claim the scoring engine cannot actually support.

`decision_record_persistence._build_score_context()` (replaces
`_build_score_contributions()`) now returns exactly ONE candidate-level
structure, never a per-component list:

```python
{
    "score_breakdown": {"<component>": <value>, ...},   # parsed, not recomputed
    "candidate_evidence_record_ids": [...],              # Task 12.1's list, read verbatim
    "candidate_evidence_identities": [...],               # same ids, deduplicated by article/evidence identity
    "attribution_level": "candidate",
    "component_attribution_available": False,
}
```

- `score_breakdown` is the SAME already-computed value (an existing
  `CandidateAssessment` field, persisted verbatim for the first time in
  round 2), merely parsed via the existing
  `score_breakdown_schema.parse_score_breakdown()` for readability.
- `candidate_evidence_record_ids`/`candidate_evidence_identities` are Task
  12.1's existing `applicability_summary["evidence_record_ids"]`, with
  duplicate ARTICLE identities collapsed (e.g. the same article reaching
  this candidate via two different `evidence_records` rows — PubMed and
  Europe PMC each independently saved — collapses to one identity). This IS
  real, honest metadata deduplication; it is NOT claimed to prevent
  duplicate SCORE, because the `score_breakdown` value itself was already
  computed upstream, before this module ever sees the record.
- `attribution_level`/`component_attribution_available` exist specifically
  so no downstream reader of this JSON can mistake "candidate-level" for
  "per-component" — the second field is hard-coded `False`, never
  conditionally `True`, because no scoring-engine change was made.
- `score_breakdown_schema.dedupe_score_contributions()` is NOT called here
  anymore — using it would require pairing evidence with a specific
  component, exactly the fabricated link this round removes. The function
  itself is untouched and still tested in `score_breakdown_schema.py`.

`_PERSISTED_RECORD_FIELDS` gained `score_context` (replacing
`score_contributions`) — `_serialize_record()` builds it the same way as
before (special-cased, not read off `as_dict` directly), documented inline.

**Tests:** the returned structure is asserted to have `attribution_level ==
"candidate"`, `component_attribution_available is False`, and no
`"component"` key anywhere in it; a persisted decision record's JSON blob is
asserted to contain `score_context` and NOT `score_contributions`; a
dedicated test asserts `decision_record_persistence` no longer even imports
`dedupe_score_contributions`.

## 5. First author in insert-time fuzzy fallback (issue 4)

The `sources` table has no author column — this was already true in round 2
and remains true (no migration was added; see section 8 for why). Round 2's
`articles_equivalent()` silently skipped the author check whenever either
side lacked an author, which meant the "title + year + author" fallback
insert-time dedup claimed in round 2's report was never actually
author-gated in practice (the existing side can never provide one).

**Fix chosen: option 2 from the review (tighten the guard, document the
real behavior), not option 1 (fabricate author extraction from an
unverified schema).** Repository-wide inspection (repeated from round 2,
unchanged) confirms no connector extracts author metadata and the `sources`
table has no author column — there is nothing to extract without guessing
at an unverified API field or adding a migration, both explicitly out of
scope.

`deduplication_engine.articles_equivalent()` now has two similarity
thresholds, both documented module-level constants:

- `FUZZY_TITLE_SIMILARITY_THRESHOLD = 0.92` — used when a first author IS
  verifiable and matches on both sides.
- `FUZZY_TITLE_SIMILARITY_THRESHOLD_UNVERIFIED_AUTHOR = 0.97` — used
  whenever author cannot be verified on both sides (the guaranteed case for
  `database._find_existing_evidence_by_fuzzy_title()`, since `sources` never
  carries one). An unverifiable author now COSTS precision (a stricter bar)
  instead of silently costing nothing.

`_find_existing_evidence_by_fuzzy_title()`'s docstring states plainly: this
is a title+year fallback with a raised similarity bar when author can't be
confirmed, not a title+year+author match. It never claims otherwise. A
dedicated test (`test_r3_issue4_insert_time_author_check_documented_as_title_year_only`)
asserts the docstring says so.

**Tests:** similar title + same year + different author, when author is
verifiable on both sides → not duplicate (the strict pre-existing check);
existing author unretrievable + title only moderately similar → not
duplicate (fails the 0.97 bar); punctuation/subtitle-only variation with a
long, specific title and same year → duplicate accepted (clears the 0.97
bar even without an author check).

## 6. False-positive test matrix (issue 5)

`test_phase2_evidence_architecture.py`'s `test_r3_issue5_matrix_*` group
implements the exact 7-row matrix from the review: DOI-exact/outcome-different
→ two Evidence; DOI-exact/direction-different → two Evidence; PMID-exact/
claim-same → one Evidence; fuzzy-title/outcome-different → two Evidence;
fuzzy-title/claim-same → one Evidence; title-year-similar/author-different →
two articles; URL-same/population-different → two Evidence.

## 7. Files changed (round 3)

- `deduplication_engine.py` — `evidence_contexts_equivalent()` (new);
  `_evidence_context_components()` (new, shared helper factored out of
  `compute_evidence_identity()`); `_fuzzy_collapse_remaining()` now requires
  both `articles_equivalent()` and `evidence_contexts_equivalent()`;
  `articles_equivalent()` gained the unverified-author stricter threshold.
- `database.py` — `_find_existing_evidence_by_identity()` and
  `_find_existing_evidence_by_fuzzy_title()` rewritten as genuine two-phase
  lookups; new `_fetch_evidence_identity_candidates()` helper (bounded,
  degrade-to-None-on-ambiguity); both now call
  `evidence_contexts_equivalent()` instead of re-deriving full identity.
- `decision_record_persistence.py` — `_build_score_contributions()` replaced
  by `_build_score_context()`; `_PERSISTED_RECORD_FIELDS`'s
  `"score_contributions"` entry replaced by `"score_context"`; the
  `dedupe_score_contributions` import removed (no longer called from this
  module).
- `test_phase2_evidence_architecture.py` — round-2's `test_issue2_*` group
  rewritten for the new honest `score_context` shape; ~23 new tests added
  covering issues 1/2/4/5 of this round via both pure-function assertions
  and a new in-memory fake-Supabase harness (`_InsertTimeHarness`) that
  exercises `save_evidence_record()` end-to-end.
- `test_task12_1_decision_record_evidence_traceability.py`,
  `test_decision_record_persistence.py` — the two pre-existing
  `_PERSISTED_RECORD_FIELDS`-lock tests updated to expect `score_context`
  instead of `score_contributions` (the field this phase intentionally
  renamed) — same maintenance pattern as every prior phase that
  intentionally grew/changed this allowlist; no assertion was weakened.
- `PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md` — addendum updated (not the
  original pre-Phase-2 audit body) with round-3 findings.
- `PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md` — this file, rewritten in
  place.

`score_breakdown_schema.py` is UNCHANGED in this round — its
`dedupe_score_contributions()`/`score_contribution_key()` utilities remain
exactly as built in round 1, simply no longer called from
`decision_record_persistence.py`.

## 8. Remaining limitations (restated, round 3)

- **Duplicate score-contribution prevention inside the scoring engine is
  not done and is explicitly out of scope** — see section 1. This is the
  headline limitation of this phase and is not described as completed
  anywhere in this report.
- **No connector extracts author metadata; `sources` has no author
  column.** Unchanged from round 2. The insert-time fuzzy fallback is
  honestly a title+year comparison with a raised bar, not a
  title+year+author comparison, and is now documented as such everywhere
  it's discussed (code docstrings and this report).
- **`preparation`/`dose` still have no dedicated `evidence_records` SQL
  column** — unchanged from round 2.
- **Fuzzy matching cost is bounded but not free** — unchanged from round 2
  (O(bucket²) at read time within a plant/indication/dosage bucket; up to
  `limit(200)` extra `sources` queries per insert-time fallback call; now
  also up to one extra `evidence_records` query per fuzzy-matched source
  candidate at insert time, still bounded per-candidate, not a scan).
- **A fuzzy-matched (not exactly-title-matched) article whose evidence
  context otherwise matches may still fail to dedupe** in a narrow edge
  case: phase 2's `evidence_contexts_equivalent()` check does not depend on
  exact article-title equality, so this is NOT the source of any new false
  negative — this note is retained from round 2 only for the case where a
  near-miss (not exact) title comparison was involved in establishing the
  article match; round 3's fix does not reintroduce or worsen this.
- **`scientific_evidence_collector.py`** remains untouched, unchanged from
  round 1/2.

## 9. Migration / deployment actions required

**None**, unchanged from rounds 1 and 2. No new column, table, or migration
file was introduced in round 3. `score_context` is a new key inside the
already-JSON `decision_records.records` blob column, not a new SQL column.

## 10. Exact test execution results (round 3)

```
$ python3 -m pytest \
  test_phase1_evidence_direction.py \
  test_scientific_phrase_matcher.py \
  test_evidence_database_deduplication.py \
  test_task12_1_decision_record_evidence_traceability.py \
  test_database_evidence_schema_extension.py \
  test_evidence_normalization.py \
  test_phase2_evidence_architecture.py -q
214 passed in 2.22s

$ python3 -m pytest -q -rs        # full repository test suite
2327 passed in 54.99s
```

(2327 vs. round 2's 2304 reflects this round's net test additions minus the
handful of round-2 `test_issue2_*` tests that were rewritten in place for
the new `score_context` shape rather than left describing the removed
`score_contributions` structure.) No test was skipped, xfailed, or excluded.

One real bug was found and fixed during this round's own test-writing
process (the article-key re-derivation asymmetry described in section 2) —
disclosed there, not hidden, and re-verified passing in the run above.

## 11. Tests passed / failed / skipped

- Passed: 2327 / 2327 (full suite), including all 214 tests in the
  explicitly required regression + new-test set.
- Failed: 0. Skipped: 0.

---

# ROUND 4 ADDENDUM — legacy URL/title source-reuse path bugfix

## What was found

`database.save_evidence_record()`'s pre-existing legacy path — used to
find/reuse a `sources` row by URL or title — still contained the exact bug
already fixed elsewhere in round 3: after finding `existing_source_id`, it
decided Evidence duplication with a bare

```python
supabase.table("evidence_records").select("id")
    .eq("plant_id", plant_id).eq("source_id", existing_source_id)
    .eq("target_indication", ...).eq("dosage_form", ...)
    .limit(1).execute()
```

— no comparison of outcome, direction, population, dose, plant part, or
claim at all. A same-URL/title article with a genuinely different Evidence
context (different outcome, different direction, etc.) was silently
collapsed to the first matching row. This is the same "article identity
mixed with evidence identity" defect round 3 fixed on the DOI/PMID/NCT_ID
path and the fuzzy-title path — it had simply not been applied to this
third, older path yet.

## Fix

The legacy URL/title path now does exactly what the review specified:

1. `existing_source_id = _find_existing_source(...)` — unchanged, still the
   one place a `sources` row is found/reused by URL then title.
2. If a source was found, candidates sharing that `source_id` (and the same
   `plant_id`/`target_indication`/`dosage_form`) are fetched WITH full
   context via `_fetch_evidence_identity_candidates()` — the exact same
   helper `_find_existing_evidence_by_identity()` and
   `_find_existing_evidence_by_fuzzy_title()` already use. No new, parallel
   DOI/PMID/fuzzy logic was written.
3. Each candidate is compared via
   `deduplication_engine.evidence_contexts_equivalent(record, candidate_row)`
   — the same function used everywhere else in this phase.
4. Only an exact evidence-context match returns the existing id.
5. When the article matches (same `source_id`) but no candidate's context
   matches, `existing_source_id` is still REUSED (no second `sources` row
   for the same article) — the function falls through to the normal insert
   path below with `source_id = existing_source_id`, so a new
   `evidence_records` row is created, correctly, without duplicating the
   `sources` row.
6. Ambiguity handling: `_fetch_evidence_identity_candidates()` returning
   `None` (unresolvable query) is treated identically to an empty
   candidate list — "cannot confirm a duplicate, keep the record" — per
   the review's explicit instruction that a false duplicate is more
   dangerous than a temporary duplicate.

## Tests added (`test_r4_*` in `test_phase2_evidence_architecture.py`)

All run end-to-end against `save_evidence_record()` with a real (small,
in-memory) fake Supabase client — not just the helper functions in
isolation:

- Same URL + outcome different → two Evidence, one `sources` row.
- Same URL + direction different → two Evidence, one `sources` row.
- Same URL + population different → two Evidence, one `sources` row.
- Same URL + plant part different → two Evidence, one `sources` row.
- Same URL + context fully identical → one Evidence.
- Same title, empty URL, context different → two Evidence, one `sources`
  row (exercises the title branch of `_find_existing_source()`, not just
  the URL branch).
- The DOI, PMID, and NCT paths (already fixed in round 3) re-verified
  passing unchanged after this round's edit — nothing on those paths was
  touched.
- An explicit regression test,
  `test_r4_regression_legacy_path_no_longer_dedupes_on_source_plant_indication_dosage_alone`,
  documents in its own docstring exactly the bug this round fixed and
  locks in that a same-source/plant/indication/dosage-form pair with a
  different outcome produces two rows sharing one `source_id`.

## Files changed, round 4

- `database.py` — the legacy URL/title path inside `save_evidence_record()`
  rewritten as described above. No other function in this file changed.
- `test_phase2_evidence_architecture.py` — `_InsertTimeHarness`'s `sources`
  table select handling extended to support `url`/`title` filters (it
  previously only supported the `year` filter used by the fuzzy-title
  path), so the new tests could exercise `_find_existing_source()`'s real
  query shape; 10 new `test_r4_*` tests added.
- `PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md` — addendum extended (original
  audit body and round 1-3 addenda untouched).
- `PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md` — this addendum.

## Exact test execution results, round 4

```
$ python3 -m pytest \
  test_phase1_evidence_direction.py \
  test_scientific_phrase_matcher.py \
  test_evidence_database_deduplication.py \
  test_task12_1_decision_record_evidence_traceability.py \
  test_database_evidence_schema_extension.py \
  test_evidence_normalization.py \
  test_phase2_evidence_architecture.py -q
224 passed in 2.07s

$ python3 -m pytest -q -rs        # full repository test suite
2337 passed in 53.86s
```

No test was skipped, xfailed, or excluded. No new failure was introduced by
this round's fix against any pre-existing test.

## Tests passed / failed / skipped, round 4

- Passed: 2337 / 2337 (full suite), including all 224 tests in the
  explicitly required regression + new-test set.
- Failed: 0. Skipped: 0.

---

# ROUND 5 ADDENDUM — Dose / Preparation identity vs. persistence gap

## What was found

`deduplication_engine._evidence_context_components()` (and therefore both
`compute_evidence_identity()` and `evidence_contexts_equivalent()`) have
compared `dose` and `preparation` since round 1. Neither was ever persisted
anywhere on `evidence_records`, and `_fetch_evidence_identity_candidates()`
never fetched either — so the database side of every comparison always saw
both as empty, regardless of what a new record carried. A genuinely
duplicate Evidence with a populated Dose or Preparation on the new side
could be treated as distinct from an identical existing row purely because
the existing row could never carry that value.

## Schema check performed before choosing a fix

`migrations/` was inspected first, as required. No `dose` or `preparation`
column exists in any migration file (`0002`, `0004`, `0005`). This is
"Case 2" from the review brief (columns do not exist).

## Fix chosen: minimal, idempotent migration — following the repository's own established pattern

The repository already has a documented, safe-to-defer, safe-to-run-
multiple-times pattern for exactly this situation
(`migrations/0002_extend_evidence_records.sql`: `ALTER TABLE evidence_records
ADD COLUMN IF NOT EXISTS <col> <type>`, nullable, no default, paired with
`_OPTIONAL_EVIDENCE_COLUMNS` + a PGRST204 retry in Python). Reusing this
exact, already-established idiom was judged the right choice over
overloading an existing JSON/JSONB column (`effect_size`/`p_value`/
`adverse_events`/`interactions_structured` all hold a different, more
complex shape already, and stuffing two more concepts into one of them
would make future queries and indexing harder, not easier, for no real
benefit — this table's own precedent is one column per concept).

**New migration files** (same header/rollback-file convention as `0002`,
`0004`, `0005`):
- `migrations/0006_add_dose_preparation.sql` — `ALTER TABLE evidence_records
  ADD COLUMN IF NOT EXISTS dose TEXT, ADD COLUMN IF NOT EXISTS preparation
  TEXT;`
- `migrations/0006_add_dose_preparation_down.sql` — the paired rollback.

**`preparation` is NOT `extraction_method`.** The migration's own header
documents why (same reasoning already established in
`standard_evidence_schema.py`'s `_LEGACY_FIELD_MAP` comment): preparation
describes how the herbal material was prepared for the studied Evidence
item; extraction_method is a compound-extraction/solvent concept
historically tracked on the separate `plant_compounds` table. A dedicated
test (`test_r5_preparation_and_extraction_method_remain_independent`)
locks in that `Extraction_Method` never participates in evidence identity
and `Preparation` alone drives the outcome, in both directions.

## Where Dose and Preparation are persisted

`database.save_evidence_record()`'s `evidence_payload` dict gained:

```python
"dose": record.get("Dose") or None,
"preparation": record.get("Preparation") or None,
```

— same `.get(key) or None` discipline as every other Phase-2-added field on
this payload (never a guessed/fabricated value; `None` means "not
provided," not "empty string"). Both are also added to
`_OPTIONAL_EVIDENCE_COLUMNS` (so `_insert_evidence_with_optional_schema_fallback()`'s
existing PGRST204 retry loop already tolerates an unmigrated deployment
with zero new code) and to `load_evidence_records()`'s output mapping
(`"Dose": item.get("dose")`, `"Preparation": item.get("preparation")`), so
the read-time DataFrame path (`evidence_database.py` /
`deduplication_engine.deduplicate_evidence()`) also sees real values
instead of always-missing ones.

## How candidate fetch retrieves them

`_fetch_evidence_identity_candidates()`'s `optional_columns` list grew from
`["plant_part"]` to `["plant_part", "dose", "preparation"]`, and its
single-column retry was generalized into a loop that removes whichever
optional column PostgREST reports missing, one at a time, up to
`len(optional_columns) + 1` attempts — never silently proceeding past a
REQUIRED column being reported missing (`doi`/`pmid`/`nct_id`/`source_id`/
`plant_id`/`target_indication`/`dosage_form` all still return `None`
immediately, exactly as before). All three `candidate_row` construction
sites (`_find_existing_evidence_by_identity()`,
`_find_existing_evidence_by_fuzzy_title()`, and the legacy URL/title path
fixed in round 4) now include `"Dose": candidate.get("dose")` and
`"Preparation": candidate.get("preparation")`.

## A second, independent bug found and fixed during this round

While writing `test_r5_url_title_same_preparation_different_two_evidence`,
it failed even after the persistence fix above — two Evidence with
different `Preparation` were still being collapsed to one. Root cause:
`_evidence_context_components()`'s preparation line read only
`_get_any(row, "preparation")` (the canonical key), missing the
`"Preparation"` legacy-key alias every OTHER dimension in that same
function already had (e.g. `_get_any(row, "dose", "Dose")`). Because
`evidence_contexts_equivalent()`/`compute_evidence_identity()` canonicalize
a plain dict input via `canonicalize_evidence_record()`, which returns a
LEGACY-shaped dict (`"Preparation"`, capital P), the preparation dimension
had been silently comparing as `""` on both sides for every plain-dict
caller since round 1 — meaning Preparation never actually differentiated
two Evidence rows in practice, independent of and prior to the persistence
gap this round's task described. Fixed by adding the missing alias:
`_get_any(row, "preparation", "Preparation")`. Disclosed here, not hidden;
caught by this round's own test-writing, not missed.

## Backward compatibility — old deployments without the migration applied

`_fetch_evidence_identity_candidates()` first attempts the full column list
(including `dose`/`preparation`); on a PGRST204 "missing column" error for
either, it retries with that column dropped from the SELECT, one at a time.
On a deployment where the migration was never applied, both columns are
simply never fetched — `dose`/`preparation` compare as `""` on the database
side of every comparison on that deployment (identical situation to
`plant_part` already had since round 3), while the other, always-present
dimensions (outcome, direction, population, study_type, notes) still fully
gate the comparison. This never produces a false duplicate — it only means
Dose/Preparation cannot yet differentiate two otherwise-identical Evidence
rows on an unmigrated deployment, which is the same, already-accepted
limitation the report has documented for `plant_part` since round 3, now
extended to two more fields. A dedicated test
(`test_r5_missing_optional_columns_deployment_falls_back_safely`) exercises
this against a fake Supabase client that raises PGRST204 for exactly these
three optional columns and confirms the function still returns usable
candidates rather than `None` or raising.

## Tests added (`test_r5_*` in `test_phase2_evidence_architecture.py`)

All run end-to-end against `save_evidence_record()`/
`_fetch_evidence_identity_candidates()` with a real fake-Supabase client:

1. Same DOI + same Dose + same context → one Evidence.
2. Same DOI + Dose different → two Evidence.
3. Same URL/title + same Preparation + same context → one Evidence.
4. Same URL/title + Preparation different → two Evidence.
5. A real insert with both Dose and Preparation set, then a candidate
   fetch, retrieves both values correctly.
6. Preparation and Extraction_Method verified independent in both
   directions.
7. A deployment missing the optional columns falls back safely (no
   exception, no false duplicate, candidates still usable).
8. The round-4 legacy-path regression test re-verified passing unchanged.

## Files changed, round 5

- `migrations/0006_add_dose_preparation.sql` (new).
- `migrations/0006_add_dose_preparation_down.sql` (new).
- `database.py` — `_OPTIONAL_EVIDENCE_COLUMNS` gained `dose`/`preparation`;
  `evidence_payload` gained both fields; `load_evidence_records()` gained
  both fields; `_fetch_evidence_identity_candidates()` generalized to a
  multi-optional-column retry loop; all three `candidate_row` construction
  sites gained `Dose`/`Preparation`.
- `deduplication_engine.py` — one-line bugfix: `_get_any(row, "preparation",
  "Preparation")`.
- `test_phase2_evidence_architecture.py` — 8 new `test_r5_*` tests.
- `PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md` — addendum extended.
- `PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md` — this addendum.

## Exact test execution results, round 5

```
$ python3 -m pytest \
  test_phase1_evidence_direction.py \
  test_scientific_phrase_matcher.py \
  test_evidence_database_deduplication.py \
  test_task12_1_decision_record_evidence_traceability.py \
  test_database_evidence_schema_extension.py \
  test_evidence_normalization.py \
  test_phase2_evidence_architecture.py -q
232 passed in 2.28s

$ python3 -m pytest -q -rs        # full repository test suite
2345 passed in 56.03s
```

No test was skipped, xfailed, or excluded.

## Tests passed / failed / skipped, round 5

- Passed: 2345 / 2345 (full suite), including all 232 tests in the
  explicitly required regression + new-test set.
- Failed: 0. Skipped: 0.
