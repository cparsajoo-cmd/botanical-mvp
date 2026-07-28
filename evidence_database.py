import pandas as pd

from database import load_evidence_records, get_evidence_record_count
from deduplication_engine import deduplicate_evidence


def load_evidence_database():
    """The platform's single production evidence-read path.

    Task: activate deduplication (previously an orphaned module — see
    deduplication_engine.py's own docstring history / ARCHITECTURE.md).
    This is the one place load_evidence_records()'s raw rows are turned
    into the DataFrame every downstream caller actually consumes —
    BotanicalRDCandidateEngine (via this function), app.py's Supabase
    preview panel (via load_evidence_database_with_meta below), and
    pages/Plant_Profile.py — so deduplicating here, once, means every
    caller gets deduplicated evidence without a second/parallel
    deduplication path being added anywhere else.

    deduplicate_evidence() collapses records that share the same
    source (by URL, falling back to title, falling back to a Notes
    snippet) for the same plant/indication/dosage_form combination,
    keeping the highest-scoring copy. This is a study-level dedup
    layer on top of database.save_evidence_record()'s existing
    insert-time check (which only prevents an exact
    source_id/indication/dosage_form combination from being inserted
    twice) — it also catches near-duplicates that arrive with a
    different URL/title from different connectors (e.g. the same
    trial indexed by both PubMed and Europe PMC).
    """
    return deduplicate_evidence(load_evidence_records())


def load_evidence_database_with_meta():
    """Same data as load_evidence_database(), plus an explicit report of
    what was actually retrieved — data_source_mode, total row count on
    the server vs. rows actually returned, and whether the fetch looks
    complete. Added as a separate function (rather than changing
    load_evidence_database()'s return shape) so every existing caller
    of load_evidence_database() keeps working unchanged; only call
    sites that actually need to SHOW completeness/fallback status to a
    user (currently: app.py's Supabase preview panel) need to switch to
    this one.

    Completeness (is_complete/returned_records/total_records) is
    computed against the RAW fetch from Supabase, before
    deduplication — deduplication removing rows must never be
    misreported as an incomplete fetch. The DataFrame actually
    returned to the caller, however, is the deduplicated one (the
    same one load_evidence_database() would return), since this
    function's df is what app.py puts on screen and stores in
    st.session_state["evidence_df"] for other steps to read.

    Returns (df, meta) where meta is a dict with:
      - data_source_mode: "Full Supabase data" | "Partial Supabase data"
                           | "Local fallback only" | "Unavailable"
      - total_records: server-reported exact row count, or None if it
                        couldn't be determined
      - returned_records: number of rows fetched from Supabase, BEFORE
                           deduplication (used for the completeness
                           check against total_records)
      - deduplicated_records: number of rows actually returned in df,
                               AFTER deduplication
      - duplicates_removed: returned_records - deduplicated_records
      - is_complete: True only if total_records is known AND matches
                      returned_records (the raw fetch, not the
                      deduplicated count)
      - error: the exception message, if the fetch failed entirely
    """
    try:
        total_records = get_evidence_record_count()
    except Exception:
        total_records = None

    try:
        raw_df = load_evidence_records()
    except Exception as exc:
        return pd.DataFrame(), {
            "data_source_mode": "Unavailable",
            "total_records": total_records,
            "returned_records": 0,
            "deduplicated_records": 0,
            "duplicates_removed": 0,
            "is_complete": False,
            "error": str(exc),
        }

    returned_records = len(raw_df)
    if total_records is None:
        # We got rows back but couldn't independently verify the total,
        # so completeness is genuinely unknown — report that honestly
        # rather than assuming either "complete" or "partial".
        mode = "Partial Supabase data"
        is_complete = False
    elif returned_records >= total_records:
        mode = "Full Supabase data"
        is_complete = True
    else:
        mode = "Partial Supabase data"
        is_complete = False

    df = deduplicate_evidence(raw_df)
    deduplicated_records = len(df)

    return df, {
        "data_source_mode": mode,
        "total_records": total_records,
        "returned_records": returned_records,
        "deduplicated_records": deduplicated_records,
        "duplicates_removed": returned_records - deduplicated_records,
        "is_complete": is_complete,
        "error": None,
    }


def build_database_if_needed():
    return None


def load_sheet(sheet_name):
    return deduplicate_evidence(load_evidence_records())
