# Hybrid Indication-Relevance Architecture — Implementation Report

## 0. Starting condition (important context)

Before this round's work began, this repository already contained a
substantially complete implementation of the requested architecture:
`0005_add_evidence_embeddings.sql` (+ down migration), `embedding_service.py`,
`evidence_embedding_text.py`, `vector_search.py`,
`backfill_evidence_embeddings.py`, a hybrid scoring layer already added to
`general_indication_relevance.py`, production wiring already added to
`indication_candidate_discovery.py`, and `EMBEDDING_ARCHITECTURE_REVIEW.md`.
None of that code was rewritten this round — it was audited, verified
correct by direct reading against the brief's requirements, and had **zero
test coverage**, which is the actual gap this round closed. One real
production bug was found and fixed during that audit (§2).

## 1. All changed/added files this round

| File | Type | What changed |
|---|---|---|
| `candidate_shortlisting.py` | Modified | Added `MATCH_HYBRID_SEMANTIC`/`MATCH_EMBEDDING_SEMANTIC` to imports and `_MATCH_SUPPORTIVE` — see bug §2. |
| `test_embedding_architecture_unit.py` | Added | Level A: 20 unit tests. |
| `test_embedding_vector_service.py` | Added | Level B: 18 tests, OpenAI/Supabase fully mocked. |
| `test_hybrid_relevance_production_integration.py` | Added | Level C: 11 production-path integration tests. |
| `embedding_threshold_calibration.py` | Added | Level D tool: threshold sweep, precision/recall/FPR/FNR. |
| `test_embedding_threshold_calibration.py` | Added | Level D: 5 unit tests for the calibration tool itself. |
| `EMBEDDING_THRESHOLD_CALIBRATION.md` | Added | Calibration methodology + illustrative (synthetic) dry-run. |
| `IMPLEMENTATION_REPORT.md` | Added | This file. |

Not modified this round (audited and found already correct):
`0005_add_evidence_embeddings.sql`, `0005_add_evidence_embeddings_down.sql`,
`embedding_service.py`, `evidence_embedding_text.py`, `vector_search.py`,
`backfill_evidence_embeddings.py`, `general_indication_relevance.py`,
`indication_candidate_discovery.py`, `EMBEDDING_ARCHITECTURE_REVIEW.md`.

## 2. Bug found and fixed this round

`candidate_shortlisting.py`'s `_MATCH_SUPPORTIVE` tuple (used by
`_indication_relevance_detail_authoritative()` to decide which
`Indication_Match_Type` values count as supportive evidence) was written
before `MATCH_HYBRID_SEMANTIC`/`MATCH_EMBEDDING_SEMANTIC` existed, so it did
not include them. Consequence: a plant discovered and correctly included by
`discover_indication_candidates()` on the strength of an embedding-only or
hybrid match would silently score **zero** `Indication_Relevance_Score` in
the shortlist stage — the exact "discovery and shortlist disagree" failure
mode this whole architecture exists to prevent, reintroduced by omission
for the two newest match types specifically. Fixed by adding both constants
to the import and the tuple. Covered by
`test_discovery_and_shortlist_never_disagree_about_match_type_source`
(prior round) and
`test_discovery_shortlist_consistency_with_embedding_match_type` (this
round, which explicitly asserts a plant found only via
`MATCH_EMBEDDING_SEMANTIC` still gets `Indication_Relevance_Score > 0` in
the shortlist).

## 3. Test report

```
$ python -m pytest -q
1909 passed in 16.23s
```

Breakdown of the 54 tests added this round:
- Level A (unit): 20 — canonical embedding text, deterministic hashing,
  exclusion of safety fields from efficacy text, exclusion of
  ChEBI/patent/DailyMed proxy records, hybrid score components, fallback
  degradation (verified byte-for-byte equal to the pure deterministic
  engine's own answer when `embedding_similarity=None`).
- Level B (vector-service, fully mocked): 18 — `embed_query()` called
  exactly once per invocation and never raises; batching splits correctly
  at the configured batch size; retry with exponential backoff recovers
  from transient failures and gives up after `max_retries`; one failed
  batch does not abort remaining batches; idempotent upsert; content-hash
  gated skip/re-embed; a stored hash under an old `embedding_version` is
  correctly invisible to a query for the new version (forces refresh); RPC
  call shape and failure-returns-empty-list behavior.
- Level C (production-path integration): 11 — unseen synonym discovered via
  mocked embedding similarity alone (zero shared lexical token by
  construction); negative control (generic clinical language, no
  embedding match, correctly excluded); plant isolation (a high similarity
  score attached to one plant's record is structurally incapable of
  affecting another plant, verified by mocking a similarity for only one
  of two otherwise-identical unrelated records); discovery/shortlist
  consistency for an embedding-driven match (this is what caught the bug
  in §2); embedding-provider-failure and RPC-failure fallback (both must
  not crash, both verified to still find the plant via the deterministic
  engine); diabetes/cough/migraine regressions unaffected by the embedding
  wiring; Ginkgo structured safety/interaction/reassurance regression with
  the embedding infrastructure present but unavailable; compound-source
  mode confirmed to never touch `Indication_Match_Type`/embedding
  infrastructure at all.
- Level D (calibration tool unit tests): 5 — metric computation correctness,
  monotonic recall-vs-threshold behavior, best-F1 selection does not
  degenerate to a trivial threshold.

Two test-construction mistakes of mine (not engine bugs) were caught by
the test run and fixed during development: accidental literal word overlap
between a query and its own "negative control" mock text (twice, in
different tests) — both are explained inline in
`test_hybrid_relevance_production_integration.py` where they occurred, not
hidden.

Full previously-existing suite (1855 tests as of the last round, including
all Gold Case, Safety_Flags, and general-indication-relevance-wiring
regressions) remains green, unmodified, and was re-run in full above, not
sampled.

## 4. Proof: query embedding generated once per Step 5 run

`indication_candidate_discovery.py:678`:
```python
query_embedding = embed_query(indication)
```
This call sits once, outside the per-plant `for _, item in
candidates.iterrows():` loop (which starts later in the same function) and
outside the per-record loop nested inside it. Confirmed empirically by
`test_embed_query_calls_openai_exactly_once` (Level B, direct) and by every
Level C test that patches `icd.embed_query` with a `side_effect` tracking
function — none of them observe more than one call for a run involving
multiple plants and multiple records per plant.

## 5. Proof: evidence embeddings are stored and reused, not recomputed per run

`backfill_evidence_embeddings.py` is the only writer of `evidence_embeddings`
rows — it runs offline, via CLI, not during a Step 5 request.
`indication_candidate_discovery.py`'s runtime path only ever *reads* via
`match_evidence_embeddings()` (one `SELECT`-shaped RPC call, §4's sibling
call at line 685) — it contains no code path that calls
`embed_texts_batched()` or `upsert_evidence_embeddings()`. Content-hash
gating (`fetch_existing_content_hashes()` vs. each candidate's freshly
computed hash) means even the offline backfill only pays for an embedding
call when a record's canonical text has actually changed —
`test_backfill_skips_unchanged_hash_and_reembeds_changed_one` and
`test_hash_gated_skip_logic_directly` verify this directly.

## 6. Proof: no disease-specific vocabulary was added

- `indication_semantics.py` was not modified this round (not in the
  changed-files list in §1).
- `general_indication_relevance.py`'s stopword list and `HYBRID_WEIGHTS`/
  threshold constants were not modified this round.
- `test_cough_regression_no_hardcoded_cough_vocabulary_added` asserts the
  `"Cough"` family in `INDICATION_SEMANTICS` is the pre-existing one, not a
  new addition, and the Cough/Migraine regression tests both find their
  target plant via evidence phrased with **zero literal indication word**
  ("antitussive"/"expectorant" for Cough; "CGRP"/"headache frequency" for
  Migraine) plus the *general* corpus-adaptive and embedding machinery —
  not a per-disease rule.
- The one genuinely new synthetic indication used across this round's tests
  (`"juvenile nocturnal enuresis symptom relief"`, and, in the prior
  round's surviving test file, `"zelunergic mucosal discomfort"`) exists
  nowhere in source code outside the test files that invented it.

## 7. Proof: candidate_shortlisting.py does not recalculate relevance

```
$ grep -n "embed\|Embedding\|openai\|OpenAI" candidate_shortlisting.py
(no matches)
```
`candidate_shortlisting.py` imports no embedding-related name and calls no
embedding-related function, directly or transitively — confirmed by
`test_compound_source_mode_never_touches_embedding_infrastructure` (Level C)
and by the grep above having zero hits. Its relevance scoring
(`_indication_relevance_detail_authoritative`) reads `Indication_Match_Type`/
`Indication_Match_Terms` — values already computed once, upstream, by
`discover_indication_candidates()` — and only falls back to independently
resolving `indication_semantics.py`
(`_indication_relevance_detail_legacy_fallback`) when those columns are
entirely absent from the input rows (compound-source mode, or a
hand-built legacy DataFrame), a path unchanged by this round and exercised
by its own dedicated test.

## 8. Known limitations and operational cost

- **No real embedding or real Supabase call was made anywhere in this
  development process.** Every embedding-related test in this repository
  mocks the OpenAI client and/or the Supabase RPC/table interface. The
  request/response shapes match the documented `openai==2.45.0` SDK and
  `supabase-py` interfaces already used elsewhere in this repository
  (`llm_extractor.py`, `database.py`), but have not been exercised against
  the real services. First real use (a real backfill run, or the first
  Step 5 run after the migration is applied and `OPENAI_API_KEY` is
  configured) is the first point at which any of this is validated against
  live infrastructure — recommend a small `--limit 5 --dry-run` backfill
  first, then a small real backfill, then a Step 5 run with a known Gold
  Case query, before a full backfill.
- **Threshold calibration is not yet real** (§ EMBEDDING_THRESHOLD_CALIBRATION.md).
  The provisional weights/thresholds in `general_indication_relevance.py`
  are reasonable starting points, not validated ones.
- **A pre-existing, unrelated bug remains open** (documented in the prior
  round's `STEP5_GENERAL_INDICATION_RELEVANCE_PRODUCTION_COMPLETION.md`):
  `_pick_from_row`'s priority-ordered column selection keeps only the
  first populated column when a single evidence row has both
  `Adverse_Events`/`Interactions_Structured` and `Safety_Findings`
  populated at once. Not touched this round; still flagged rather than
  silently left undocumented.
- **Operational cost**: one query embedding per Step 5 run (negligible;
  `text-embedding-3-small` is OpenAI's lowest-cost embedding tier) plus a
  one-time backfill cost proportional to the number of *distinct* evidence
  records (content-hash gating means re-running the backfill after it has
  already completed costs approximately nothing until evidence content
  actually changes). Exact current OpenAI pricing was not verified against
  a live source in this environment (no web access) — confirm current
  per-token pricing before committing to a backfill budget, per
  `EMBEDDING_ARCHITECTURE_REVIEW.md` section 11.
- **The HNSW index and RPC function have not been executed against a real
  Postgres/pgvector instance.** The SQL in `0005_add_evidence_embeddings.sql`
  was written and reviewed against pgvector's documented syntax but not
  run — applying it in a Supabase SQL editor and confirming
  `CREATE EXTENSION vector` succeeds is the first real-world validation
  step, per the migration file's own header comment.
