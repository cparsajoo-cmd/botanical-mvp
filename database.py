import pandas as pd
from supabase_client import get_supabase_client


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

            "Reference_Count": 1,
            "Source_Type": source.get("source_type", ""),
            "Source_Title": source.get("title", ""),
            "Source_Organization": source.get("organization", ""),
            "Source_Year": source.get("year", ""),
            "Source_URL": source.get("url", ""),
        })

    return pd.DataFrame(rows)
