"""Backfill missing canonical scientific assertions in Supabase.

Usage:
  python backfill_canonical_assertions.py              # dry-run
  python backfill_canonical_assertions.py --apply      # write missing fields
  python backfill_canonical_assertions.py --apply --limit 500

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
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

from database import get_supabase_client
from llm_extractor import extract_evidence_with_llm
from supabase_data import _fetch_table_df

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


def backfill(*, apply=False, limit=None, sleep_fn=time.sleep):
    supabase = get_supabase_client()

    # Ordered, paginated, retried-per-page fetch -- see the module
    # docstring's bug #1. strict=True: a page that never succeeds after
    # retries must raise (IncompletePaginationError) rather than let this
    # backfill quietly treat a partial table as the whole table, exactly
    # the failure mode strict mode exists to rule out for the embedding
    # backfill.
    df = _fetch_table_df(
        "evidence_records", select_expr=SELECT_EXPR, order_by="id", strict=True
    )
    rows = df.to_dict(orient="records")
    if limit:
        rows = rows[: int(limit)]

    stats = BackfillCanonicalAssertionsStats()
    failures = []

    for item in rows:
        stats.scanned += 1

        # A source/connector assertion is already higher-authority than an LLM
        # extraction, and an existing LLM assertion must never be overwritten.
        # Therefore either populated direction means this row needs no direction
        # backfill. Keeping the old stats field name avoids breaking callers.
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
            # Nothing for the LLM to read -- would only ever come back
            # "Unknown" at the cost of a real API call. Kept as its own
            # bucket rather than silently folded into `failed` or
            # `extracted`, so a full-run reconciliation can tell "no
            # source text exists" apart from "extraction was attempted".
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
                # CRITICAL provenance boundary: values returned by
                # extract_evidence_with_llm() are model-derived assertions, not
                # source/connector assertions. Never write them into
                # result_direction / safety_signal. The production engine already
                # transports these dedicated LLM fields separately and resolves
                # them below source assertions in canonical precedence.
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
        except Exception as exc:  # noqa: BLE001 - captured into failures, not swallowed
            stats.failed += 1
            failures.append({"id": item.get("id"), "error": str(exc)})

    return stats, failures


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    stats, failures = backfill(apply=args.apply, limit=args.limit)
    print(stats.as_log_line())
    if failures:
        print("Failures:")
        for row in failures[:20]:
            print(row)
