import streamlit as st
import pandas as pd

from evidence_database import load_evidence_database
from source_ingestion_engine import normalize_source_record
from database import save_evidence_record


st.set_page_config(
    page_title="Source Ingestion",
    page_icon="📥",
    layout="wide"
)

st.title("📥 Source Ingestion")
st.caption("Convert scientific source information into structured evidence records")

df = load_evidence_database()

st.markdown("## Add a new evidence record")

with st.form("source_ingestion_form"):

    col1, col2 = st.columns(2)

    with col1:
        scientific_name = st.text_input("Scientific name")
        common_name = st.text_input("Common name")

        product_type = st.selectbox(
            "Product type",
            [
                "Herbal product",
                "Food supplement",
                "Cosmetic",
                "Medical device",
                "Veterinary botanical product",
            ]
        )

        dosage_form = st.selectbox(
            "Dosage form",
            [
                "Infusion",
                "Capsule",
                "Tablet",
                "Syrup",
                "Cream",
                "Gel",
                "Mouthwash",
                "Nasal spray",
                "Chewing gum",
                "Powder",
                "Extract",
            ]
        )

        target_indication = st.selectbox(
            "Target indication",
            [
                "Sleep and relaxation",
                "Constipation",
                "Cough",
                "Digestive comfort",
                "Anxiety",
                "Skin inflammation",
                "Dry mouth",
                "Allergic rhinitis",
                "IBS",
                "Wound healing",
            ]
        )

        target_market = st.selectbox(
            "Target market",
            [
                "European Union",
                "France",
                "United States",
                "Canada",
                "Iran",
            ]
        )

    with col2:
        source_type = st.selectbox(
            "Source type",
            [
                "EMA-HMPC",
                "WHO monograph",
                "ESCOP monograph",
                "Pharmacopoeia",
                "RCT",
                "Meta-analysis",
                "Review",
                "Market data",
                "Other",
            ]
        )

        source_title = st.text_input("Source title")
        source_organization = st.text_input("Source organization")
        source_year = st.text_input("Source year")
        source_url = st.text_input("Source URL / DOI")

        ema_status = st.selectbox("EMA status", ["", "Yes", "No", "To verify"])
        who_status = st.selectbox("WHO status", ["", "Yes", "No", "To verify"])
        escop_status = st.selectbox("ESCOP status", ["", "Yes", "No", "To verify"])

    st.markdown("## Evidence assessment")

    col3, col4 = st.columns(2)

    with col3:
        clinical_level = st.selectbox(
            "Clinical level",
            ["", "Strong", "Moderate", "Weak", "Not found"]
        )

        clinical_rct_count = st.number_input(
            "Clinical RCT count",
            min_value=0,
            step=1
        )

        meta_level = st.selectbox(
            "Meta-analysis level",
            ["", "Strong", "Moderate", "Weak", "Not found"]
        )

        meta_count = st.number_input(
            "Meta-analysis count",
            min_value=0,
            step=1
        )

    with col4:
        infusion_evidence = st.selectbox(
            "Dosage-form specific evidence",
            ["", "Direct", "Indirect", "Not found"]
        )

        safety_level = st.selectbox(
            "Safety level",
            ["", "Good", "Acceptable", "Caution", "High risk"]
        )

        drug_interaction_level = st.selectbox(
            "Drug interaction level",
            ["", "Low", "Moderate", "High", "Unknown"]
        )

        commercial_level = st.selectbox(
            "Commercial level",
            ["", "High", "Medium", "Low", "Unknown"]
        )

    regulatory_status = st.text_input("Regulatory status")

    novel_food_status = st.selectbox(
        "Novel food status",
        ["", "No", "Yes", "To verify"]
    )

    notes = st.text_area("Notes / extracted evidence")

    submitted = st.form_submit_button("Save evidence record to database")

if submitted:

    raw_record = {
        "Plant_ID": len(df) + 1,
        "Scientific_Name": scientific_name,
        "Common_Name": common_name,
        "Product_Type": product_type,
        "Dosage_Form": dosage_form,
        "Target_Indication": target_indication,
        "Target_Market": target_market,
        "EMA_Status": ema_status,
        "WHO_Status": who_status,
        "ESCOP_Status": escop_status,
        "Clinical_Level": clinical_level,
        "Clinical_RCT_Count": clinical_rct_count,
        "Meta_Level": meta_level,
        "Meta_Count": meta_count,
        "Infusion_Evidence": infusion_evidence,
        "Safety_Level": safety_level,
        "Drug_Interaction_Level": drug_interaction_level,
        "Commercial_Level": commercial_level,
        "Regulatory_Status": regulatory_status,
        "Novel_Food_Status": novel_food_status,
        "Reference_Count": 1,
        "Notes": notes,
        "Source_Type": source_type,
        "Source_Title": source_title,
        "Source_Organization": source_organization,
        "Source_Year": source_year,
        "Source_URL": source_url,
    }

    record = normalize_source_record(raw_record)

    row_id = save_evidence_record(record)

    st.success(f"Evidence record saved to database. Row ID: {row_id}")

    st.markdown("## Saved record preview")
    st.dataframe(pd.DataFrame([record]), use_container_width=True)

    csv = pd.DataFrame([record]).to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download saved evidence record as CSV",
        data=csv,
        file_name="saved_evidence_record.csv",
        mime="text/csv"
    )
