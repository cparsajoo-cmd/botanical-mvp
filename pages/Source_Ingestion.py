import streamlit as st
import pandas as pd

from evidence_extractor import extract_evidence_from_text
from source_ingestion_engine import normalize_source_record
from database import save_evidence_record


st.set_page_config(
    page_title="Source Ingestion",
    page_icon="📥",
    layout="wide"
)

st.title("📥 Source Ingestion")
st.caption("Paste scientific source text, extract fields, then save a structured evidence record")

st.markdown("## 1. Paste source text")

source_text = st.text_area(
    "Source text",
    height=250,
    placeholder="Paste text from EMA, WHO, ESCOP, PubMed abstract, monograph, or report..."
)

if st.button("Extract fields from source text", type="primary"):
    if not source_text.strip():
        st.warning("Please paste source text first.")
    else:
        extracted = extract_evidence_from_text(source_text)
        st.session_state["extracted_record"] = extracted
        st.success("Fields extracted. Review and edit below.")

record = st.session_state.get("extracted_record", {})

st.markdown("## 2. Review and edit extracted record")

with st.form("source_ingestion_form"):

    col1, col2 = st.columns(2)

    with col1:
        scientific_name = st.text_input(
            "Scientific name",
            value=record.get("Scientific_Name", "")
        )

        common_name = st.text_input(
            "Common name",
            value=record.get("Common_Name", "")
        )

        product_type = st.selectbox(
            "Product type",
            [
                "Herbal product",
                "Food supplement",
                "Cosmetic",
                "Medical device",
                "Veterinary botanical product",
            ],
            index=0
        )

        dosage_options = [
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

        dosage_value = record.get("Dosage_Form", "")
        dosage_index = dosage_options.index(dosage_value) if dosage_value in dosage_options else 0

        dosage_form = st.selectbox(
            "Dosage form",
            dosage_options,
            index=dosage_index
        )

        indication_options = [
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

        indication_value = record.get("Target_Indication", "")
        indication_index = indication_options.index(indication_value) if indication_value in indication_options else 0

        target_indication = st.selectbox(
            "Target indication",
            indication_options,
            index=indication_index
        )

        market_options = [
            "European Union",
            "France",
            "United States",
            "Canada",
            "Iran",
        ]

        market_value = record.get("Target_Market", "European Union")
        market_index = market_options.index(market_value) if market_value in market_options else 0

        target_market = st.selectbox(
            "Target market",
            market_options,
            index=market_index
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

        status_options = ["", "Yes", "No", "To verify"]

        ema_value = record.get("EMA_Status", "")
        ema_index = status_options.index(ema_value) if ema_value in status_options else 0

        ema_status = st.selectbox(
            "EMA status",
            status_options,
            index=ema_index
        )

        who_value = record.get("WHO_Status", "")
        who_index = status_options.index(who_value) if who_value in status_options else 0

        who_status = st.selectbox(
            "WHO status",
            status_options,
            index=who_index
        )

        escop_value = record.get("ESCOP_Status", "")
        escop_index = status_options.index(escop_value) if escop_value in status_options else 0

        escop_status = st.selectbox(
            "ESCOP status",
            status_options,
            index=escop_index
        )

    st.markdown("## 3. Evidence assessment")

    col3, col4 = st.columns(2)

    with col3:
        clinical_options = ["", "Strong", "Moderate", "Weak", "Not found"]

        clinical_value = record.get("Clinical_Level", "")
        clinical_index = clinical_options.index(clinical_value) if clinical_value in clinical_options else 0

        clinical_level = st.selectbox(
            "Clinical level",
            clinical_options,
            index=clinical_index
        )

        clinical_rct_count = st.number_input(
            "Clinical RCT count",
            min_value=0,
            step=1,
            value=int(record.get("Clinical_RCT_Count", 0) or 0)
        )

        meta_options = ["", "Strong", "Moderate", "Weak", "Not found"]

        meta_value = record.get("Meta_Level", "")
        meta_index = meta_options.index(meta_value) if meta_value in meta_options else 0

        meta_level = st.selectbox(
            "Meta-analysis level",
            meta_options,
            index=meta_index
        )

        meta_count = st.number_input(
            "Meta-analysis count",
            min_value=0,
            step=1,
            value=int(record.get("Meta_Count", 0) or 0)
        )

    with col4:
        dosage_evidence_options = ["", "Direct", "Indirect", "Not found"]

        infusion_value = record.get("Infusion_Evidence", "")
        infusion_index = dosage_evidence_options.index(infusion_value) if infusion_value in dosage_evidence_options else 0

        infusion_evidence = st.selectbox(
            "Dosage-form specific evidence",
            dosage_evidence_options,
            index=infusion_index
        )

        safety_options = ["", "Good", "Acceptable", "Caution", "High risk", "Unknown"]

        safety_value = record.get("Safety_Level", "")
        safety_index = safety_options.index(safety_value) if safety_value in safety_options else 0

        safety_level = st.selectbox(
            "Safety level",
            safety_options,
            index=safety_index
        )

        drug_interaction_level = st.selectbox(
            "Drug interaction level",
            ["", "Low", "Moderate", "High", "Unknown"]
        )

        commercial_level = st.selectbox(
            "Commercial level",
            ["", "High", "Medium", "Low", "Unknown"]
        )

    regulatory_status = st.text_input(
        "Regulatory status",
        value=record.get("Regulatory_Status", "")
    )

    novel_food_status = st.selectbox(
        "Novel food status",
        ["", "No", "Yes", "To verify"]
    )

    notes = st.text_area(
        "Notes / extracted evidence",
        value=record.get("Notes", ""),
        height=200
    )

    submitted = st.form_submit_button("Save evidence record to database")


if submitted:

    if not scientific_name.strip():
        st.error("Scientific name is required.")
    else:
        raw_record = {
            "Plant_ID": "",
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

        final_record = normalize_source_record(raw_record)

        row_id = save_evidence_record(final_record)

        st.success(f"Evidence record saved to database. Row ID: {row_id}")

        st.markdown("## Saved record preview")
        st.dataframe(pd.DataFrame([final_record]), use_container_width=True)
