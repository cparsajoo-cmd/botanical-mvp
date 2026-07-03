import pandas as pd
from supabase_client import get_supabase_client


def save_evidence_record(record):
    supabase = get_supabase_client()

    plant_result = supabase.table("plants").insert({
        "scientific_name": record.get("Scientific_Name", ""),
        "common_name": record.get("Common_Name", ""),
    }).execute()

    plant_id = plant_result.data[0]["id"]

    source_result = supabase.table("sources").insert({
        "source_type": record.get("Source_Type", ""),
        "organization": record.get("Source_Organization", ""),
        "title": record.get("Source_Title", ""),
        "year": record.get("Source_Year", ""),
        "url": record.get("Source_URL", ""),
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
        "clinical_rct_count": int(record.get("Clinical_RCT_Count", 0) or 0),
        "meta_level": record.get("Meta_Level", ""),
        "meta_count": int(record.get("Meta_Count", 0) or 0),

        "dosage_form_evidence": record.get(
            "Dosage_Form_Evidence",
            record.get("Infusion_Evidence", "")
        ),

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
        "regulatory_evidence": record.get("Regulatory_Evidence", ""),
        "safety_confidence": record.get("Safety_Confidence", ""),
        "commercial_confidence": record.get("Commercial_Confidence", ""),
        "extracted_indication": record.get("Extracted_Indication", ""),
        "extracted_dosage_form": record.get("Extracted_Dosage_Form", ""),
        "evidence_score": int(record.get("Evidence_Score", 0) or 0),
    }).execute()

    return evidence_result.data[0]["id"]


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
            "Regulatory_Evidence": item.get("regulatory_evidence", ""),
            "Safety_Confidence": item.get("safety_confidence", ""),
            "Commercial_Confidence": item.get("commercial_confidence", ""),
            "Extracted_Indication": item.get("extracted_indication", ""),
            "Extracted_Dosage_Form": item.get("extracted_dosage_form", ""),
            "Evidence_Score": item.get("evidence_score", 0),

            "Reference_Count": 1,
            "Source_Type": source.get("source_type", ""),
            "Source_Title": source.get("title", ""),
            "Source_Organization": source.get("organization", ""),
            "Source_Year": source.get("year", ""),
            "Source_URL": source.get("url", ""),
        })

    return pd.DataFrame(rows)
