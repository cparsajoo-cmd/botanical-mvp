# Audit: `backfill_canonical_assertions.py` (2026-08-08)

## Why this file, not a new one

The repo already contains everything Option 2 (LLM-based Evidence Direction)
needs, just not wired together:

- `llm_extractor.py` — a real, working OpenAI extraction call
  (`extract_evidence_with_llm`) that returns a structured `result_direction`.
- `canonical_scientific_assertion.py` — `resolve_record_direction()` already
  prefers a structured direction over the raw-text regex classifier
  (`evidence_interpretation.classify_evidence_direction`), and only falls
  back to the regex classifier when no structured direction exists at all.
- `backfill_canonical_assertions.py` — already exists to populate that
  structured direction for old rows that predate this pipeline.

So the missing piece was never "build an LLM classifier" — it's "make sure
every evidence record actually has a structured direction, so the resolver
never needs its text fallback." This audit reviewed the existing backfill
script the same way every other change in this repo has been reviewed:
read the real code, don't assume the previous version was correct, verify
with tests before claiming anything is fixed.

## Bugs found and fixed

### 1. Silent pagination truncation (same bug class as the 11195/21806 incident)

The previous version issued one unbounded
`.select(...).execute()` with no `.order()`/`.range()`. PostgREST caps an
unbounded select at its own default page size. On the real
`evidence_records` table (21,900+ rows) this script would have silently
scanned only the first page and reported `failed=0` — indistinguishable
from success — having never looked at the rest of the table.

**Fix:** reuse `supabase_data._fetch_table_df()` (already ordered,
paginated, retried per page, and available in `strict=True` mode) instead
of re-implementing pagination a third time. `strict=True` means a page
that never succeeds after retries raises `IncompletePaginationError`
instead of being silently treated as "the whole table."

### 2. Missing article title in the extraction prompt

`llm_extractor.extract_evidence_with_llm()` builds its prompt from
`record.get("Source_Title", "")` and `record.get("Notes", "")`. The
previous `select(...)` never fetched a title column and never set
`Source_Title` on the record dict, so every backfill extraction ran with
an empty title — silently discarding context every other caller of this
function provides.

**Fix:** joined `sources(title)` and populated `Source_Title`.

### 3. No retry for transient OpenAI failures

A bulk run over thousands of rows makes an occasional transient
timeout/5xx likely. The previous version treated any exception as a
permanent per-row failure.

**Fix:** added a bounded retry (2 retries, `0.5 * (attempt + 1)` s
backoff — same convention as `supabase_data.py`'s page retries).

### 4. `None` becoming `NaN` after the DataFrame round-trip

Found by the tests themselves, not by inspection: switching the fetch to
`_fetch_table_df()` (fix #1) meant rows now pass through a pandas
DataFrame. A SQL `NULL` (`None` in the raw Supabase response) becomes a
float `NaN` after `.to_dict(orient="records")`. The existing `_blank()`
helper only checked `v is None`, so a genuinely-empty
`result_direction`/`safety_signal` read as "already has a value"
(`str(nan)` is `"nan"`, non-blank) — which would have made the
never-overwrite guard skip every row in the table.

**Fix:** `_blank()` now also treats `NaN` as blank. Caught by
`test_never_overwrites_existing_result_direction` and
`test_safety_signal_backfilled_only_when_blank` before this was shipped.

## What did NOT change

- CLI flags (`--apply`, `--limit`) and dry-run-by-default behavior.
- The rule that an existing `result_direction`/`safety_signal` is never
  overwritten.
- `llm_extractor.py` and `canonical_scientific_assertion.py` themselves —
  out of scope for this pass, not touched.

## What this does NOT fix yet

This backfill only reaches the **per-record** structured direction. Two
things upstream of it still matter and were confirmed still true by
reading the code, not assumed:

1. The main production scoring path
   (`botanical_rd_candidate_engine.py::_collect_raw_evidence` →
   `interpret_evidence`) still never calls `resolve_record_direction()` at
   all — it pools raw text across every contributing record into one blob
   and always runs the regex classifier on that blob, even for records
   that now have a structured `result_direction`. Backfilling the data
   does nothing for the app's own Overall_Score/R&D_Opportunity_Score
   until this call site is changed to check structured direction
   per-record first.
2. `evidence_body_assessment.py` (used by `final_decision_policy.py`, the
   Reference-Grounded Validation decision path) already calls
   `resolve_record_direction()` correctly — it will automatically benefit
   from this backfill without further code changes, for any record this
   backfill actually reaches.

## Test coverage added

`test_backfill_canonical_assertions.py` — 11 tests, all passing:

- Pagination scans every row across multiple pages (2,500 synthetic rows,
  proves bug #1 is fixed) + a sanity check that the fake client itself
  would catch a regression back to unordered pagination.
- `Source_Title` reaches the extractor (proves bug #2 is fixed).
- Existing `result_direction`/`safety_signal` is never overwritten
  (proves bug #4 is fixed — this test failed against the un-patched
  `_blank()` before the fix).
- Rows with no `Notes` and no title are never sent to the LLM
  (`skipped_no_extractable_text`), and are still accounted for in
  reconciliation.
- Transient failure retried then succeeds; retries exhausted still
  records a failure (never silently skipped).
- `apply=False` never calls `.update()`.
- `--limit` takes the first N of the ordered fetch (deterministic sample).
- Full-run stats reconcile exactly (`scanned == skipped_has_direction +
  skipped_no_extractable_text + extracted + failed`) across a mixed batch.

Full existing suite re-run after this change: same 9 pre-existing
failures present with these two files removed from the tree entirely
(confirmed by quarantining them and re-running) — unrelated to this
change, not introduced by it, listed here for visibility rather than
silently ignored:

- `test_benchmark_harness.py` (3 tests)
- `test_independent_holdout_e2e.py` (1 test)
- `test_phase4_eligibility_gate_desired_behavior.py` (1 test)
- `test_structural_leakage_boundary.py` (3 tests)
- `test_structured_final_decision_authority.py` (1 test)

These look related to the `EngineEvidenceInput`/eligibility-gate/decision
work reflected elsewhere in this snapshot (extra fields on
`EngineEvidenceInput` beyond the 4 the test expects, and decision-status
mismatches), not to evidence direction — flagged here for your review
rather than touched, since that's a different subsystem than this audit's
scope.

## Suggested next step

Wire `resolve_record_direction()` into
`botanical_rd_candidate_engine.py::_collect_raw_evidence`/`interpret_evidence`
per-record, before the pooled-text fallback (item #1 under "What this
does NOT fix yet"). That is what would actually change the app's own
Overall_Score, not just the validation reports.
