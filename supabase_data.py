"""
Loaders for the real Supabase tables that back the central engine:
plant_compounds, compound_profiles, scientific_evidence.

These are the primary data source for BotanicalRDCandidateEngine.
Every loader is defensive: if Supabase is unreachable, misconfigured, or
a table is empty, it returns an empty DataFrame rather than raising, so
the engine can fall back to its small local seed dataset instead of
crashing the app.
"""

import pandas as pd

from supabase_client import get_supabase_client


def _fetch_table_df(table_name, page_size=1000):
    supabase = get_supabase_client()

    all_rows = []
    start = 0

    while True:
        response = (
            supabase.table(table_name)
            .select("*")
            .range(start, start + page_size - 1)
            .execute()
        )
        rows = response.data or []
        all_rows.extend(rows)

        if len(rows) < page_size:
            break

        start += page_size

    return pd.DataFrame(all_rows)


def load_plant_compounds_df():
    try:
        return _fetch_table_df("plant_compounds")
    except Exception:
        return pd.DataFrame()


def load_compound_profiles_df():
    try:
        return _fetch_table_df("compound_profiles")
    except Exception:
        return pd.DataFrame()


def load_scientific_evidence_df():
    try:
        return _fetch_table_df("scientific_evidence")
    except Exception:
        return pd.DataFrame()
