import pandas as pd
from supabase_client import get_supabase_client

# ======================================================================
# Task 10.2 — REQUIRED SUPABASE SCHEMA CHANGE (not performed by this
# repository; no migration mechanism exists for any table here — see
# ARCHITECTURE.md's "Known oddities" and telemetry_persistence.py's/
# decision_record_persistence.py's identical precedent).
#
# save_evidence_record() below now writes, and load_evidence_records()
# now reads, five additional TEXT columns on the existing evidence_records
# table, plus reads (never writes) the table's own existing primary key:
#
#   applicability_classification         TEXT
#   applicability_rationale              TEXT
#   applicability_evaluated_dimensions   TEXT
#   applicability_missing_dimensions     TEXT
#   applicability_detected_mismatches    TEXT
#   id                                   (already exists as the table's
#                                          primary key — only newly READ
#                                          here, not newly written)
#
# Until an operator adds the five new columns by hand in Supabase:
#   - save_evidence_record()'s insert will raise a PostgREST
#     "column ... does not exist" error for the whole row (see the
#     inline comment at the insert call site for which callers catch
#     this and which don't) — existing columns are unaffected.
#   - load_evidence_records() degrades gracefully: item.get(<new key>, "")
#     simply returns "" for a column that doesn't exist in the response,
#     so existing callers and existing rows are unaffected either way.
# This module does not attempt to create the columns itself, matching
# every other persistence module in this repository.
# ======================================================================


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _find_existing_source(supabase, url, title):
    if url:
        res = supabase.table("sources").select("id").eq("url", url).limit(1).execute()
        if res.data:
            return res.data[0]["id"]

    if title:
        res = supabase.table("sources").select("id").eq("title", title).limit(1).execute()
        if res.data:
            return res.data[0]["id"]

    return None


def _get_or_create_plant(supabase, scientific_name, common_name):
    scientific_name = scientific_name or ""

    if scientific_name:
        res = supabase.table("plants").select("id").eq("scientific_name", scientific_name).limit(1).execute()
        if res.data:
            return res.data[0]["id"]

    plant_result = supabase.table("plants").insert({
        "scientific_name": scientific_name,
        "common_name": common_name or "",
    }).execute()

    return plant_result.data[0]["id"]


def save_evidence_record(record):
    supabase = get_supabase_client()

    source_url = record.get("Source_URL", "")
    source_title = record.get("Source_Title", "")

    existing_source_id = _find_existing_source(
        supabase=supabase,
        url=source_url,
        title=source_title,
    )

    if existing_source_id:
        existing_evidence = (
            supabase.table("evidence_records")
            .select("id")
            .eq("source_id", existing_source_id)
            .eq("target_indication", record.get("Target_Indication", ""))
            .eq("dosage_form", record.get("Dosage_Form", ""))
            .limit(1)
            .execute()
        )

        if existing_evidence.data:
            return existing_evidence.data[0]["id"]

    plant_id = _get_or_create_plant(
        supabase=supabase,
        scientific_name=record.get("Scientific_Name", ""),
        common_name=record.get("Common_Name", ""),
    )

    if existing_source_id:
        source_id = existing_source_id
    else:
        source_result = supabase.table("sources").insert({
            "source_type": record.get("Source_Type", ""),
            "organization": record.get("Source_Organization", ""),
            "title": source_title,
            "year": record.get("Source_Year", ""),
            "url": source_url,
            "raw_text": record.get("Notes", ""),
        }).execute()
        source_id = source_result.data[0]["id"]

    evidence_result = supabase.table("evidence_records").insert({
        "plant_id": plant_id,
        "source_id": source_id,

        "product_type": record.get("Product_Type", ""),
        "dosage_form": record.get("Dosage_Form", ""),
        "target_indication": record.get("Target_Indication", ""),
        "target_market": record.get("Target_Market", ""),

        "ema_status": record.get("EMA_Status", ""),
        "who_status": record.get("WHO_Status", ""),
        "escop_status": record.get("ESCOP_Status", ""),

        "clinical_level": record.get("Clinical_Level", ""),
        "clinical_rct_count": _safe_int(record.get("Clinical_RCT_Count", 0)),
        "meta_level": record.get("Meta_Level", ""),
        "meta_count": _safe_int(record.get("Meta_Count", 0)),

        "dosage_form_evidence": record.get("Dosage_Form_Evidence", record.get("Infusion_Evidence", "")),
        "safety_level": record.get("Safety_Level", ""),
        "drug_interaction_level": record.get("Drug_Interaction_Level", ""),
        "commercial_level": record.get("Commercial_Level", ""),
        "regulatory_status": record.get("Regulatory_Status", ""),
        "novel_food_status": record.get("Novel_Food_Status", ""),
        "notes": record.get("Notes", ""),

        "evidence_type": record.get("Evidence_Type", ""),
        "evidence_level": record.get("Evidence_Level", ""),
        "dosage_form_relevance": record.get("Dosage_Form_Relevance", ""),
        "study_model": record.get("Study_Model", ""),
        "detected_dosage_forms": record.get("Detected_Dosage_Forms", ""),
        "detected_indications": record.get("Detected_Indications", ""),
        "regulatory_evidence": record.get("Regulatory_Evidence", ""),
        "evidence_score": _safe_int(record.get("Evidence_Score", 0)),

        "plant": record.get("Plant", ""),
        "study_type": record.get("Study_Type", ""),
        "dosage_form_detected": record.get("Dosage_Form_Detected", ""),
        "target_indication_detected": record.get("Target_Indication_Detected", ""),
        "population": record.get("Population", ""),
        "sample_size": record.get("Sample_Size", ""),
        "comparator": record.get("Comparator", ""),
        "primary_outcome": record.get("Primary_Outcome", ""),
        "result_direction": record.get("Result_Direction", ""),
        "safety_signal": record.get("Safety_Signal", ""),
        "direct_for_selected_product": record.get("Direct_For_Selected_Product", ""),
        "directness_reason": record.get("Directness_Reason", ""),

        # Task 10.2 — Evidence-level Preparation Applicability. Additive
        # only; never overwrites/duplicates direct_for_selected_product/
        # directness_reason above. REQUIRES these five columns to exist
        # on the real Supabase evidence_records table before this will
        # persist anything — see REQUIRED_SUPABASE_COLUMNS_TASK_10_2 at
        # the top of this module. Like every other table in this
        # repository, there is no migration file; until the columns are
        # added by hand in Supabase, this insert raises a PostgREST
        # "column does not exist" error, exactly like adding any other
        # new column to this dict would. save_evidence_record() itself
        # has never caught its own exceptions (true before this task
        # too — every field in this insert shares this risk). Whether a
        # caller sees that raised exception or a graceful per-record
        # error depends on the caller: multi_source_collector.py's
        # _save_records_from_connector() wraps this call in a per-record
        # try/except and reports failures in its `errors` list (the
        # dominant, Step-2 production path); evidence_collector.py's
        # collect_pubmed_evidence() and source_pipeline.py's
        # run_source_pipeline() do not wrap this call and would
        # propagate the exception. This is pre-existing behavior,
        # unchanged by this task.
        "applicability_classification": record.get("Applicability_Classification", ""),
        "applicability_rationale": record.get("Applicability_Rationale", ""),
        "applicability_evaluated_dimensions": record.get("Applicability_Evaluated_Dimensions", ""),
        "applicability_missing_dimensions": record.get("Applicability_Missing_Dimensions", ""),
        "applicability_detected_mismatches": record.get("Applicability_Detected_Mismatches", ""),
    }).execute()

    return evidence_result.data[0]["id"]


def get_evidence_record_count():
    """Total row count in evidence_records, without fetching row bodies.

    Uses PostgREST's exact count (returned in the response metadata
    regardless of how many rows are actually returned) combined with
    range(0, 0) so at most one row's data crosses the wire. This lets
    the UI show "N total records" without paying for a full-table fetch
    just to find out N.
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("evidence_records")
        .select("id", count="exact")
        .range(0, 0)
        .execute()
    )
    return response.count if response.count is not None else 0


def load_evidence_records():
    supabase = get_supabase_client()

    response = supabase.table("evidence_records").select(
        "*, plants(scientific_name, common_name), sources(*)"
    ).execute()

    rows = []

    for item in response.data:
        plant = item.get("plants") or {}
        source = item.get("sources") or {}

        rows.append({
            "Plant_ID": item.get("plant_id", ""),
            "Scientific_Name": plant.get("scientific_name", ""),
            "Common_Name": plant.get("common_name", ""),

            "Product_Type": item.get("product_type", ""),
            "Dosage_Form": item.get("dosage_form", ""),
            "Target_Indication": item.get("target_indication", ""),
            "Target_Market": item.get("target_market", ""),

            "EMA_Status": item.get("ema_status", ""),
            "WHO_Status": item.get("who_status", ""),
            "ESCOP_Status": item.get("escop_status", ""),

            "Clinical_Level": item.get("clinical_level", ""),
            "Clinical_RCT_Count": item.get("clinical_rct_count", 0),
            "Meta_Level": item.get("meta_level", ""),
            "Meta_Count": item.get("meta_count", 0),

            "Dosage_Form_Evidence": item.get("dosage_form_evidence", ""),
            "Infusion_Evidence": item.get("dosage_form_evidence", ""),

            "Safety_Level": item.get("safety_level", ""),
            "Drug_Interaction_Level": item.get("drug_interaction_level", ""),
            "Commercial_Level": item.get("commercial_level", ""),
            "Regulatory_Status": item.get("regulatory_status", ""),
            "Novel_Food_Status": item.get("novel_food_status", ""),
            "Notes": item.get("notes", ""),

            "Evidence_Type": item.get("evidence_type", ""),
            "Evidence_Level": item.get("evidence_level", ""),
            "Dosage_Form_Relevance": item.get("dosage_form_relevance", ""),
            "Study_Model": item.get("study_model", ""),
            "Detected_Dosage_Forms": item.get("detected_dosage_forms", ""),
            "Detected_Indications": item.get("detected_indications", ""),
            "Regulatory_Evidence": item.get("regulatory_evidence", ""),
            "Evidence_Score": item.get("evidence_score", 0),

            "Plant": item.get("plant", ""),
            "Study_Type": item.get("study_type", ""),
            "Dosage_Form_Detected": item.get("dosage_form_detected", ""),
            "Target_Indication_Detected": item.get("target_indication_detected", ""),
            "Population": item.get("population", ""),
            "Sample_Size": item.get("sample_size", ""),
            "Comparator": item.get("comparator", ""),
            "Primary_Outcome": item.get("primary_outcome", ""),
            "Result_Direction": item.get("result_direction", ""),
            "Safety_Signal": item.get("safety_signal", ""),
            "Direct_For_Selected_Product": item.get("direct_for_selected_product", ""),
            "Directness_Reason": item.get("directness_reason", ""),

            # Task 10.2. .get(..., "") on a column that does not exist
            # yet on the real Supabase table simply returns "" (item is
            # a plain dict from PostgREST's response — a missing key
            # behaves exactly like an existing-but-null one), so old
            # rows / a not-yet-migrated table degrade to "" here rather
            # than raising — no caller needs to change to tolerate the
            # column's absence.
            "Applicability_Classification": item.get("applicability_classification", ""),
            "Applicability_Rationale": item.get("applicability_rationale", ""),
            "Applicability_Evaluated_Dimensions": item.get("applicability_evaluated_dimensions", ""),
            "Applicability_Missing_Dimensions": item.get("applicability_missing_dimensions", ""),
            "Applicability_Detected_Mismatches": item.get("applicability_detected_mismatches", ""),

            # Task 10.2 — previously discarded on read (id was selected
            # implicitly via "*" but never mapped into the returned row
            # dict). Needed so a candidate's Applicability_Summary can
            # cite the exact evidence_records row(s) it was built from,
            # not just a plant/compound name (rule: "Do not claim
            # traceability merely through plant or compound names").
            "Evidence_Record_ID": item.get("id", ""),

            "Reference_Count": 1,
            "Source_Type": source.get("source_type", ""),
            "Source_Title": source.get("title", ""),
            "Source_Organization": source.get("organization", ""),
            "Source_Year": source.get("year", ""),
            "Source_URL": source.get("url", ""),
        })

    return pd.DataFrame(rows)
