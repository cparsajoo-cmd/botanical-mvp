import pandas as pd

from database import load_evidence_records, get_evidence_record_count


def load_evidence_database():
    return load_evidence_records()


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

    Returns (df, meta) where meta is a dict with:
      - data_source_mode: "Full Supabase data" | "Partial Supabase data"
                           | "Local fallback only" | "Unavailable"
      - total_records: server-reported exact row count, or None if it
                        couldn't be determined
      - returned_records: len(df)
      - is_complete: True only if total_records is known AND matches
                      returned_records
      - error: the exception message, if the fetch failed entirely
    """
    try:
        total_records = get_evidence_record_count()
    except Exception:
        total_records = None

    try:
        df = load_evidence_records()
    except Exception as exc:
        return pd.DataFrame(), {
            "data_source_mode": "Unavailable",
            "total_records": total_records,
            "returned_records": 0,
            "is_complete": False,
            "error": str(exc),
        }

    returned_records = len(df)
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

    return df, {
        "data_source_mode": mode,
        "total_records": total_records,
        "returned_records": returned_records,
        "is_complete": is_complete,
        "error": None,
    }


def build_database_if_needed():
    return None


def load_sheet(sheet_name):
    return load_evidence_records()
