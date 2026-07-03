import os
import pandas as pd
from supabase import create_client

try:
    import streamlit as st
except Exception:
    st = None


def get_secret(name):
    if st is not None and name in st.secrets:
        return st.secrets[name]
    return os.getenv(name)


def get_client():
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing.")

    return create_client(url, key)


def save_evidence_record(record):
    supabase = get_client()

    plant_data = {
        "scientific_name": record.get("Scientific_Name", ""),
        "common_name": record.get("Common_Name", ""),
    }

    plant_result = (
        supabase.table("plants")
        .insert(plant_data)
        .execute()
    )

    plant_id = plant_result.data[0]["id"]

    source_data = {
        "source_type": record.get("Source_Type", ""),
        "organization": record.get("Source_Organization", ""),
        "title": record.get("Source_Title", ""),
        "year": record.get("Source_Year", ""),
        "url": record.get("Source_URL", ""),
        "raw_text": record.get("Notes", ""),
    }

    source_result = (
        supabase.table("sources")
        .insert(source_data)
        .execute()
    )

    source_id = source_result.data[0]["id"]

    evidence_data = {
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
        "dosage_form_evidence": record.get("Infusion_Evidence", ""),
        "safety_level": record.get("Safety_Level", ""),
        "drug_interaction_level": record.get("Drug_Interaction_Level", ""),
        "commercial_level": record.get("Commercial_Level", ""),
        "regulatory_status": record.get("Regulatory_Status", ""),
        "novel_food_status": record.get("Novel_Food_Status", ""),
        "notes": record.get("Notes", ""),
    }

    evidence_result = (
        supabase.table("evidence_records")
        .insert(evidence_data)
        .execute()
    )

    return evidence_result.data[0]["id"]


def load_evidence_records():
    supabase = get_client()

    evidence = (
        supabase.table("evidence_records")
        .select("*, plants(scientific_name, common_name), sources(*)")
        .execute()
    )

    rows = []

    for item in evidence.data:
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
            "Infusion_Evidence": item.get("dosage_form_evidence", ""),
            "Safety_Level": item.get("safety_level", ""),
            "Drug_Interaction_Level": item.get("drug_interaction_level", ""),
            "Commercial_Level": item.get("commercial_level", ""),
            "Regulatory_Status": item.get("regulatory_status", ""),
            "Novel_Food_Status": item.get("novel_food_status", ""),
            "Reference_Count": 1,
            "Notes": item.get("notes", ""),
            "Source_Type": source.get("source_type", ""),
            "Source_Title": source.get("title", ""),
            "Source_Organization": source.get("organization", ""),
            "Source_Year": source.get("year", ""),
            "Source_URL": source.get("url", ""),
        })

    return pd.DataFrame(rows)
