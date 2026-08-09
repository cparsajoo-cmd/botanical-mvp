"""Backfill missing canonical scientific assertions in Supabase.

Usage:
  python backfill_canonical_assertions.py --limit 100       # dry-run one bounded batch
  python backfill_canonical_assertions.py --apply --limit 500  # write one bounded batch

Each invocation fetches ONLY rows whose source and LLM direction fields are
still NULL, ordered by id and capped by --limit. Re-running apply mode therefore
continues from the next unfinished rows instead of downloading the whole table.

Requirements for --apply:
- SUPABASE_URL / SUPABASE_KEY
- OPENAI_API_KEY

This script never overwrites an existing source/connector Result_Direction or
Safety_Signal, and it never stores model output in those source-authoritative
columns. LLM-derived values are written only to llm_result_direction and
llm_safety_signal so provenance remains explicit end-to-end.
It exists because pre-canonical evidence rows otherwise remain permanently
unstructured and force the engine to abstain (see
canonical_scientific_assertion.resolve_record_direction()'s fail-safe rule
and the Reference-Grounded Validation v2 root-cause finding that motivated
this audit).

AUDIT NOTE (2026-08-08) -- two real bugs found and fixed in this pass,
both discovered by re-checking the actual code rather than assuming the
previous version was correct:

1. Silent pagination truncation. The previous version issued a single
   unbounded ``.select(...).execute()`` with no ``.range()``/``.order()``.
   PostgREST caps an unbounded select at its own default row limit, so on
   the real evidence_records table (21,900+ rows) this script only ever
   scanned the first page and reported success (``failed=0``) having
   silently never looked at the rest of the table -- the exact same bug
   class documented in supabase_data.py's ``_fetch_table_df()`` (see that
   module's docstring for the original 11195/21806 incident) and in
   embedding_service.py's ``fetch_existing_content_hashes()``. Fixed by
   reusing ``supabase_data._fetch_table_df()`` directly (ordered,
   paginated, retried per page, ``strict=True`` so a page that never
   succeeds raises instead of being silently treated as "done") rather
   than re-implementing pagination a third time.

2. Missing article title in the extraction prompt. ``llm_extractor.
   extract_evidence_with_llm()`` builds its prompt from
   ``record.get("Source_Title", "")`` and ``record.get("Notes", "")``.
   The previous version's ``select(...)`` never fetched a title column and
   never populated ``Source_Title`` on the record dict it built, so every
   backfill extraction ran with an empty title -- silently discarding
   context every other caller of this same function provides. Fixed by
   joining ``sources(title)`` and populating ``Source_Title``.

Also added: a light retry (transient-error backoff, matching the
``time.sleep(0.5 * (attempt + 1))`` convention already used in
supabase_data.py) around the OpenAI extraction call, since a bulk run over
thousands of rows makes an occasional transient failure likely; a
reconciliation-friendly stats dict (mirrors LoadDiagnostics's spirit in
backfill_evidence_embeddings.py) so ``scanned`` always equals the sum of
every disjoint bucket below it; and a dedicated
``skipped_no_extractable_text`` bucket so rows with neither a title nor
notes text are not sent to the LLM at all (they can only ever come back
"Unknown", which is not worth the API call and would otherwise be
indistinguishable in the stats from a row that WAS extracted).

AUDIT NOTE (2026-08-09) -- root cause of the real scanned=0 incident found
and fixed. The quota-safe rewrite of ``_fetch_candidate_batch`` (above)
filtered server-side on BOTH ``result_direction IS NULL`` AND
``llm_result_direction IS NULL``. That is wrong against the real table:
``database.py::save_evidence_record()`` writes ``result_direction=""``
(empty string), not NULL, for every legacy row that never had a
source-asserted direction -- confirmed by reading that function directly,
not assumed. So on the real ~22,570-row table almost no row has a true SQL
NULL result_direction, and PostgREST's ``is.null`` only matches true NULL
-- ANDing it with the (correctly NULL-by-default, brand-new)
llm_result_direction filter excluded essentially every row, producing
scanned=0 even though ~22,470 rows were still unprocessed. Fixed by
filtering server-side on ``llm_result_direction IS NULL`` alone -- the
column this script owns and controls end-to-end -- and leaving the
existing NaN/None/""-aware ``_blank()`` guard inside the row loop as the
sole gate on the legacy ``result_direction``/``safety_signal`` columns,
whatever shape (NULL, "", or a real value) they happen to hold. Proven by
test_backfill_canonical_assertions.py::
test_empty_string_result_direction_is_still_scanned_not_excluded, which
reproduces the real table's shape (22,570 rows, 100 already backfilled,
the rest with result_direction="") rather than the None-only shape the
earlier tests used.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

from database import get_supabase_client
from llm_extractor import extract_evidence_with_llm

SELECT_EXPR = (
    "id,target_indication,dosage_form,notes,evidence_type,evidence_level,"
    "study_type,result_direction,llm_result_direction,safety_signal,llm_safety_signal,"
    "plants(scientific_name),sources(title)"
)

MAX_EXTRACTION_RETRIES = 2


def _blank(v):
    """True for None, NaN, and empty/whitespace-only strings.

    _fetch_table_df() returns a pandas DataFrame -- round-tripping rows
    through it turns a SQL NULL (Python None from the raw Supabase
    response) into a float NaN, not None. The original version of this
    function only checked `v is None`, so a genuinely-empty
    result_direction/safety_signal column silently read as "has a value"
    after the DataFrame round-trip (str(nan) == "nan", which is
    non-blank) -- this would have made the never-overwrite guard below
    treat every blank row as already-filled and skip the entire table.
    Caught by test_backfill_canonical_assertions.py's mixed-row tests.
    """
    if v is None:
        return True
    if isinstance(v, float) and v != v:  # NaN != NaN is the cheapest NaN check
        return True
    return not str(v).strip()


@dataclass
class BackfillCanonicalAssertionsStats:
    """Row-count accounting across every stage of one run.

    For any run (filtered by --limit or not), the following must hold
    exactly -- ``reconciles()`` checks it -- so a future silent-drop bug
    of this same class is caught by a test rather than discovered months
    later against a live 21,900-row table:

        scanned =
            skipped_has_direction
            + skipped_no_extractable_text
            + extracted
            + failed
    """

    scanned: int = 0
    skipped_has_direction: int = 0
    skipped_no_extractable_text: int = 0
    extracted: int = 0
    failed: int = 0
    updated: int = 0

    def accounted_for(self) -> int:
        return (
            self.skipped_has_direction
            + self.skipped_no_extractable_text
            + self.extracted
            + self.failed
        )

    def reconciles(self) -> bool:
        return self.accounted_for() == self.scanned

    def as_log_line(self) -> str:
        return (
            f"scanned={self.scanned} "
            f"skipped_has_direction={self.skipped_has_direction} "
            f"skipped_no_extractable_text={self.skipped_no_extractable_text} "
            f"extracted={self.extracted} "
            f"failed={self.failed} "
            f"updated={self.updated} "
            f"reconciles={self.reconciles()}"
        )

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "skipped_has_direction": self.skipped_has_direction,
            "skipped_no_extractable_text": self.skipped_no_extractable_text,
            "extracted": self.extracted,
            "failed": self.failed,
            "updated": self.updated,
            "reconciles": self.reconciles(),
        }


def _extract_with_retry(record, *, dosage_form, indication, sleep_fn=time.sleep):
    """Calls extract_evidence_with_llm(), retrying transient failures.

    Mirrors the backoff convention already used for Supabase page retries
    in supabase_data.py (``0.5 * (attempt + 1)`` seconds). Re-raises the
    last error once retries are exhausted so the caller's existing
    per-row failure accounting is unchanged.
    """
    last_error = None
    for attempt in range(MAX_EXTRACTION_RETRIES + 1):
        try:
            return extract_evidence_with_llm(
                record,
                selected_dosage_form=dosage_form,
                selected_indication=indication,
            )
        except Exception as exc:  # noqa: BLE001 - re-raised below, not swallowed
            last_error = exc
            if attempt < MAX_EXTRACTION_RETRIES:
                sleep_fn(0.5 * (attempt + 1))
    raise last_error


def _fetch_candidate_batch(supabase, *, limit: int, sleep_fn=time.sleep):
    """Fetch only unfinished rows needed for this batch.

    The previous implementation reused the full-table pagination helper and then
    sliced locally. On a 22k+ row table that meant a --limit 100 run still
    downloaded every evidence row, unnecessarily consuming Supabase egress.

    BUG FOUND (2026-08-09 audit) that made this return scanned=0 against the
    real table: this used to also filter server-side on
    ``.is_("result_direction", "null")``. PostgREST's ``is.null`` matches only
    a true SQL NULL. But ``database.py::save_evidence_record()`` -- the actual
    ingestion path for the ~22,570 existing evidence_records rows -- writes
    ``record.get("Result_Direction", "")``, i.e. an empty string "" for every
    row that never had a source-asserted direction, not NULL. So on the real
    table almost no row has ``result_direction IS NULL``, and ANDing that
    filter with the (correctly NULL-by-default, since it's a brand-new column)
    ``llm_result_direction IS NULL`` filter excluded essentially every row --
    hence scanned=0 even though ~22,470 rows still need processing.

    Fix: filter server-side ONLY on ``llm_result_direction IS NULL`` -- the
    column this script itself owns and which is genuinely NULL for every row
    it hasn't touched yet (and non-NULL, so excluded, for the 100 rows already
    backfilled). This alone makes each run bounded, deterministic, and
    resumable: rows updated by one apply run no longer match the next run's
    filter, regardless of whatever legacy value (NULL or "") their
    result_direction column happens to hold. The existing "" vs NULL vs NaN
    aware ``_blank()`` guard on ``result_direction``/``llm_result_direction``
    inside the row loop below still runs as defense-in-depth and correctly
    routes any row that DOES have a real source direction into
    ``skipped_has_direction`` without spending an LLM call on it.
    """
    last_error = None
    for attempt in range(3):
        try:
            response = (
                supabase.table("evidence_records")
                .select(SELECT_EXPR)
                .is_("llm_result_direction", "null")
                .order("id")
                .limit(int(limit))
                .execute()
            )
            return response.data or []
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 2:
                sleep_fn(0.5 * (attempt + 1))
    raise RuntimeError(
        f"Could not fetch canonical-assertion candidate batch after 3 attempts: {last_error}"
    ) from last_error


def backfill(*, apply=False, limit=100, sleep_fn=time.sleep):
    supabase = get_supabase_client()
    limit = int(limit or 100)
    if limit < 1:
        raise ValueError("limit must be a positive integer")

    rows = _fetch_candidate_batch(supabase, limit=limit, sleep_fn=sleep_fn)

    stats = BackfillCanonicalAssertionsStats()
    failures = []

    for item in rows:
        stats.scanned += 1

        # Defense-in-depth: the server-side query already excludes these rows.
        # Keep the guard so a mocked/stale response can never overwrite an
        # existing source or LLM direction.
        if (
            not _blank(item.get("result_direction"))
            or not _blank(item.get("llm_result_direction"))
        ):
            stats.skipped_has_direction += 1
            continue

        plant = item.get("plants") or {}
        source = item.get("sources") or {}
        notes = item.get("notes") or ""
        source_title = source.get("title") or ""

        if _blank(notes) and _blank(source_title):
            stats.skipped_no_extractable_text += 1
            continue

        record = {
            "Scientific_Name": plant.get("scientific_name", ""),
            "Target_Indication": item.get("target_indication", ""),
            "Dosage_Form": item.get("dosage_form", ""),
            "Notes": notes,
            "Source_Title": source_title,
            "Evidence_Type": item.get("evidence_type", ""),
            "Evidence_Level": item.get("evidence_level", ""),
            "Study_Type": item.get("study_type", ""),
        }
        try:
            out = _extract_with_retry(
                record,
                dosage_form=record["Dosage_Form"],
                indication=record["Target_Indication"],
                sleep_fn=sleep_fn,
            )
            direction = str(out.get("result_direction") or "Unknown").strip() or "Unknown"
            safety = str(out.get("safety_signal") or "").strip()
            stats.extracted += 1
            if apply:
                payload = {"llm_result_direction": direction}
                if (
                    _blank(item.get("safety_signal"))
                    and _blank(item.get("llm_safety_signal"))
                    and safety
                ):
                    payload["llm_safety_signal"] = safety
                supabase.table("evidence_records").update(payload).eq(
                    "id", item["id"]
                ).execute()
                stats.updated += 1
        except Exception as exc:  # noqa: BLE001
            stats.failed += 1
            failures.append({"id": item.get("id"), "error": str(exc)})

    return stats, failures


@dataclass
class MultiBatchResult:
    """Cumulative outcome of running several sequential batches in one process.

    Lets one GitHub Actions run do the work of many manual clicks. Design
    choices, per the 2026-08-09 conversation that requested this:

    - Runs are still simple sequential per-row calls underneath -- this does
      NOT add concurrency/parallel OpenAI calls, which would be a separate,
      larger architecture change. It only removes the need for a human to
      re-trigger the workflow between batches.
    - Stops immediately (does not start a next batch) the moment any batch
      reports failed > 0, so a systematic problem can't silently burn through
      thousands of rows before a person notices.
    - Stops cleanly (not an error) the moment a batch scans fewer rows than
      requested, since -- given _fetch_candidate_batch's llm_result_direction
      filter -- that means every remaining row in evidence_records has already
      been processed.
    - Each batch's writes (rows already updated before a later batch fails)
      remain in Supabase; nothing is rolled back. That's intentional --
      per-row updates are already atomic and independent of each other.
    """

    batch_stats: list = field(default_factory=list)
    stopped_reason: str = ""  # "exhausted" | "batch_failed" | "max_batches_reached"

    @property
    def batches_run(self) -> int:
        return len(self.batch_stats)

    def total(self, field_name: str) -> int:
        return sum(getattr(s, field_name) for s in self.batch_stats)

    def as_summary_line(self) -> str:
        return (
            f"batches_run={self.batches_run} "
            f"stopped_reason={self.stopped_reason} "
            f"total_scanned={self.total('scanned')} "
            f"total_skipped_has_direction={self.total('skipped_has_direction')} "
            f"total_skipped_no_extractable_text={self.total('skipped_no_extractable_text')} "
            f"total_extracted={self.total('extracted')} "
            f"total_failed={self.total('failed')} "
            f"total_updated={self.total('updated')}"
        )


def run_multiple_batches(*, apply=False, limit=100, max_batches=1, sleep_fn=time.sleep):
    """Runs up to max_batches sequential calls to backfill(), stopping early
    on exhaustion (no more unprocessed rows) or on the first batch with any
    row failure. Returns (MultiBatchResult, failures_from_the_stopping_batch).
    """
    if max_batches < 1:
        raise ValueError("max_batches must be a positive integer")

    result = MultiBatchResult()
    for _ in range(max_batches):
        stats, failures = backfill(apply=apply, limit=limit, sleep_fn=sleep_fn)
        result.batch_stats.append(stats)
        print(f"batch {result.batches_run}: {stats.as_log_line()}")

        if stats.failed > 0:
            result.stopped_reason = "batch_failed"
            return result, failures

        if stats.scanned < limit:
            result.stopped_reason = "exhausted"
            return result, []

    result.stopped_reason = "max_batches_reached"
    return result, []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument(
        "--max-batches",
        type=int,
        default=1,
        help="Run up to this many sequential batches in one process, stopping "
        "early if a batch fails or if evidence_records is exhausted.",
    )
    args = ap.parse_args()

    if args.max_batches and args.max_batches > 1:
        result, failures = run_multiple_batches(
            apply=args.apply, limit=args.limit or 100, max_batches=args.max_batches
        )
        print(result.as_summary_line())
        if failures:
            print("Failures in the batch that stopped the run:")
            for row in failures[:20]:
                print(row)
        if result.stopped_reason == "batch_failed":
            raise SystemExit(1)
    else:
        stats, failures = backfill(apply=args.apply, limit=args.limit)
        print(stats.as_log_line())
        if failures:
            print("Failures:")
            for row in failures[:20]:
                print(row)
