"""
Loaders for the real Supabase tables that back the central engine:
plant_compounds, compound_profiles, scientific_evidence.

These are the primary data source for BotanicalRDCandidateEngine.
Every loader is defensive: if Supabase is unreachable, misconfigured, or
a table is empty, it returns an empty DataFrame rather than raising, so
the engine can fall back to its small local seed dataset instead of
crashing the app.
"""

import time

import pandas as pd

from supabase_client import get_supabase_client


def _fetch_table_df(table_name, page_size=1000, max_retries=3):
    """Paginated fetch with per-page retry and graceful partial-result
    handling.

    At the current data scale (plant_compounds alone is 30,000+ rows),
    a full fetch needs dozens of sequential paginated requests. The
    previous version wrapped the ENTIRE pagination loop in one try/except
    at the caller — so if even ONE page-request out of 35 failed for any
    transient reason (network blip, a slow response tripping a client
    timeout), the whole fetch raised, the caller's except-block discarded
    every row already fetched, and the engine silently fell back to the
    tiny local seed dataset (e.g. a single old manually-curated plant)
    with no visible error anywhere. That looked identical to "Supabase
    has no data for this query" even though Supabase actually had
    thousands of matching rows.

    Now: each page gets its own retry budget, and if a page ultimately
    still fails after retries, whatever pages were already fetched are
    returned instead of being thrown away.
    """
    supabase = get_supabase_client()

    all_rows = []
    start = 0

    while True:
        rows = None
        last_error = None

        for attempt in range(max_retries):
            try:
                response = (
                    supabase.table(table_name)
                    .select("*")
                    .range(start, start + page_size - 1)
                    .execute()
                )
                rows = response.data or []
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))

        if rows is None:
            # This page never succeeded even after retries. Stop here and
            # return whatever was already collected rather than losing it
            # all — a partial dataset is far more useful than silently
            # falling back to the tiny local seed data.
            print(
                f"[supabase_data] Stopped fetching '{table_name}' at row "
                f"{start} after {max_retries} failed attempts: {last_error}"
            )
            break

        all_rows.extend(rows)

        if len(rows) < page_size:
            break

        start += page_size

    return pd.DataFrame(all_rows)


def load_plant_compounds_df():
    try:
        return _fetch_table_df("plant_compounds")
    except Exception as exc:
        print(f"[supabase_data] load_plant_compounds_df failed entirely: {exc}")
        return pd.DataFrame()


def load_compound_profiles_df():
    try:
        return _fetch_table_df("compound_profiles")
    except Exception as exc:
        print(f"[supabase_data] load_compound_profiles_df failed entirely: {exc}")
        return pd.DataFrame()


def load_scientific_evidence_df():
    try:
        return _fetch_table_df("scientific_evidence")
    except Exception as exc:
        print(f"[supabase_data] load_scientific_evidence_df failed entirely: {exc}")
        return pd.DataFrame()
