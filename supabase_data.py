"""
Loaders for the real Supabase tables that back the central engine:
plant_compounds, compound_profiles, scientific_evidence, evidence_records.

These are the primary data source for BotanicalRDCandidateEngine.
Every loader is defensive: if Supabase is unreachable, misconfigured, or
a table is empty, it returns an empty DataFrame rather than raising, so
the engine can fall back to its small local seed dataset instead of
crashing the app.
"""

import time

import pandas as pd

from supabase_client import get_supabase_client


def _fetch_table_df(table_name, page_size=1000, max_retries=3, select_expr="*", order_by="id"):
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

    Each page is also requested with an explicit ``.order(order_by)``
    (the table's primary key, ``"id"`` by convention throughout this
    schema) applied BEFORE ``.range(start, end)``. PostgREST/Supabase does
    not guarantee a stable row order across separate requests unless an
    explicit order is specified -- without one, the two requests for
    ``range(0, 999)`` and ``range(1000, 1999)`` are not guaranteed to see
    the same underlying row ordering (this can shift between requests,
    especially once the query involves an embedded-resource join such as
    evidence_records' ``plants(...)``/``sources(...)`` select). That let
    pagination silently omit or re-fetch rows across page boundaries, and
    could make a later page appear shorter than ``page_size`` (ending the
    loop) well before every row had actually been returned -- exactly the
    "backfill only sees ~half the table, no error anywhere" failure mode.
    Ordering by the primary key makes each page a stable, reproducible
    slice of the table, so pagination is gapless and duplicate-free
    regardless of how many pages a full fetch needs.
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
                    .select(select_expr)
                    .order(order_by)
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


def load_evidence_records_df():
    """Load evidence records with their canonical plant and source identities.

    ``evidence_records`` stores foreign keys, so selecting only ``*`` leaves no
    scientific name for indication discovery to match. Fetch the related plant
    and source rows and flatten them into the column convention used elsewhere.
    Pagination and retry behaviour remain identical to the generic loader.
    """
    try:
        raw = _fetch_table_df(
            "evidence_records",
            select_expr="*, plants(scientific_name, common_name), sources(*)",
            order_by="id",
        )
        if raw.empty:
            return raw

        rows = []
        for item in raw.to_dict(orient="records"):
            plant = item.get("plants") or {}
            source = item.get("sources") or {}
            flat = dict(item)
            flat.update({
                "Evidence_Record_ID": item.get("id"),
                "Plant_ID": item.get("plant_id"),
                "Scientific_Name": plant.get("scientific_name", ""),
                "Common_Name": plant.get("common_name", ""),
                "Source_URL": source.get("url", ""),
                "Source_Title": source.get("title", ""),
                "Source_Type": source.get("source_type", ""),
                "Source_Raw_Text": source.get("raw_text", ""),
                "PMID": item.get("pmid"),
                "DOI": item.get("doi"),
                "NCT_ID": item.get("nct_id"),
                "Target_Indication": item.get("target_indication", ""),
                "Primary_Outcome": item.get("primary_outcome", ""),
                "Result_Direction": item.get("result_direction", ""),
                "Study_Type": item.get("study_type", ""),
                "Study_Model": item.get("study_model", ""),
                "Evidence_Level": item.get("evidence_level", ""),
                "Notes": item.get("notes", ""),
                "Mechanism": item.get("mechanism"),
                "Target": item.get("target"),
                "Administration_Route": item.get("administration_route"),
                "Plant_Part": item.get("plant_part"),
                "Extraction_Method": item.get("extraction_method"),
                "Duration": item.get("duration"),
                "Effect_Size": item.get("effect_size"),
                "P_Value": item.get("p_value"),
                "Adverse_Events": item.get("adverse_events"),
                "Interactions_Structured": item.get("interactions_structured"),
                "Data_Quality_Score": item.get("data_quality_score"),
                "Safety_Findings_Raw": item.get("safety_findings"),
                "Safety_Signal": item.get("safety_signal", ""),
                # Aliases consumed by indication_candidate_discovery.  These
                # are direct copies of persisted values, never inferred.
                "Preparation": item.get("extraction_method") or item.get("dosage_form") or item.get("administration_route"),
                "Safety_Findings": item.get("safety_findings") or item.get("adverse_events") or item.get("safety_signal"),
                "Interactions": item.get("interactions_structured"),
            })
            flat.pop("plants", None)
            flat.pop("sources", None)
            rows.append(flat)
        return pd.DataFrame(rows)
    except Exception as exc:
        print(f"[supabase_data] load_evidence_records_df failed entirely: {exc}")
        return pd.DataFrame()


def load_plants_df():
    """Load the canonical plant catalogue (scientific and common names).

    This table is intentionally small and identity-focused.  It is used by
    literature discovery to validate extracted botanical names before they are
    admitted to the candidate shortlist.
    """
    try:
        return _fetch_table_df("plants")
    except Exception as exc:
        print(f"[supabase_data] load_plants_df failed entirely: {exc}")
        return pd.DataFrame()
