import streamlit as st
import pandas as pd

from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence
from report_generator import generate_report

from evidence_extractor import extract_evidence_from_text
from source_ingestion_engine import normalize_source_record
from database import save_evidence_record

from evidence_collector import collect_pubmed_evidence


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Evidence-based botanical product decision support")

df = load_evidence_database()

tab1, tab2, tab3, tab4 = st.tabs([
    "1. Product Decision",
    "2. Source Ingestion",
    "3. PubMed Connector",
    "4. Database Preview"
])


# =========================
# TAB 1 — PRODUCT DECISION
# =========================

with tab1:
    st.markdown("## Product project inputs")

    col1, col2 = st.columns(2)

    with col1:
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

        indication = st.selectbox(
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

    with col2:
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

        market = st.selectbox(
            "Target market",
            [
                "European Union",
                "France",
                "United States",
                "Canada",
                "Iran",
            ]
        )

    evidence_strictness = st.selectbox(
        "Evidence strictness",
        [
            "Dosage-form specific only",
            "Regulatory-first",
            "Clinical-first",
            "Flexible",
        ]
    )

    st.info(
        f"Which medicinal plants are scientifically and commercially worth investing in "
        f"for **{product_type}** prepared as **{dosage_form}** for **{indication}** "
        f"in **{market}**?"
    )

    if st.button("Generate decision", type="primary"):

        retrieved = retrieve_knowledge(
            df=df,
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            market=market,
            evidence_strictness=evidence_strictness,
        )

        filtered = apply_evidence_filters(
            df=retrieved,
            dosage_form=dosage_form,
            evidence_strictness=evidence_strictness,
        )

        result = analyze_evidence(
            df=filtered,
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            market=market,
            min_score=0,
        )

        st.markdown("## Decision output")

        if result.empty:
            st.warning("No evidence records found yet for this product question.")
        else:
            st.success(str(len(result)) + " relevant plant records found.")

            for _, row in result.iterrows():
                with st.expander(
                    f"🌿 {row.get('Scientific_Name', '')} — "
                    f"{row.get('Decision_Class', '')} — "
                    f"Score {row.get('Evidence_Score', '')}/100",
                    expanded=True
                ):
                    st.write(f"**Common name:** {row.get('Common_Name', '')}")
                    st.write(f"**EMA:** {row.get('EMA_Status', '')}")
                    st.write(f"**WHO:** {row.get('WHO_Status', '')}")
                    st.write(f"**ESCOP:** {row.get('ESCOP_Status', '')}")
                    st.write(f"**Clinical level:** {row.get('Clinical_Level', '')}")
                    st.write(f"**Dosage-form evidence:** {row.get('Infusion_Evidence', '')}")
                    st.write(f"**Safety:** {row.get('Safety_Level', '')}")
                    st.write(f"**Notes:** {row.get('Notes', '')}")

            st.markdown("## Full evidence table")
            st.dataframe(result, use_container_width=True)

            csv = result.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download decision table as CSV",
                data=csv,
                file_name="botanical_decision_output.csv",
                mime="text/csv",
            )

            report_text = generate_report(
                result=result,
                product_type=product_type,
                dosage_form=dosage_form,
                indication=indication,
                market=market,
            )

            st.download_button(
                "Download decision report as TXT",
                data=report_text.encode("utf-8"),
                file_name="botanical_decision_report.txt",
                mime="text/plain",
            )


# =========================
# TAB 2 — SOURCE INGESTION
# =========================

with tab2:
    st.markdown("## Source ingestion")
    st.caption("Paste source text, extract fields, review, and save to Supabase.")

    source_text = st.text_area(
        "Paste source text",
        height=250,
        placeholder="Paste text from EMA, WHO, ESCOP, PubMed abstract, monograph, or report..."
    )

    if st.button("Extract fields from source text"):
        if not source_text.strip():
            st.warning("Please paste source text first.")
        else:
            extracted = extract_evidence_from_text(source_text)
            st.session_state["extracted_record"] = extracted
            st.success("Fields extracted.")

    record = st.session_state.get("extracted_record", {})

    with st.form("manual_source_form"):

        scientific_name = st.text_input(
            "Scientific name",
            value=record.get("Scientific_Name", "")
        )

        common_name = st.text_input(
            "Common name",
            value=record.get("Common_Name", "")
        )

        product_type_ing = st.selectbox(
            "Product type",
            ["Herbal product", "Food supplement", "Cosmetic", "Medical device"]
        )

        dosage_form_ing = st.selectbox(
            "Dosage form",
            ["Infusion", "Capsule", "Tablet", "Syrup", "Cream", "Gel", "Extract"]
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
            ["European Union", "France", "United States", "Canada", "Iran"]
        )

        ema_status = st.selectbox("EMA status", ["", "Yes", "No", "To verify"])
        who_status = st.selectbox("WHO status", ["", "Yes", "No", "To verify"])
        escop_status = st.selectbox("ESCOP status", ["", "Yes", "No", "To verify"])

        clinical_level = st.selectbox(
            "Clinical level",
            ["", "Strong", "Moderate", "Weak", "Not found"]
        )

        infusion_evidence = st.selectbox(
            "Dosage-form specific evidence",
            ["", "Direct", "Indirect", "Not found"]
        )

        safety_level = st.selectbox(
            "Safety level",
            ["", "Good", "Acceptable", "Caution", "High risk", "Unknown"]
        )

        notes = st.text_area(
            "Notes / extracted evidence",
            value=record.get("Notes", ""),
            height=180
        )

        submitted = st.form_submit_button("Save evidence record to Supabase")

    if submitted:
        raw_record = {
            "Scientific_Name": scientific_name,
            "Common_Name": common_name,
            "Product_Type": product_type_ing,
            "Dosage_Form": dosage_form_ing,
            "Target_Indication": target_indication,
            "Target_Market": target_market,
            "EMA_Status": ema_status,
            "WHO_Status": who_status,
            "ESCOP_Status": escop_status,
            "Clinical_Level": clinical_level,
            "Clinical_RCT_Count": 0,
            "Meta_Level": "Not found",
            "Meta_Count": 0,
            "Infusion_Evidence": infusion_evidence,
            "Safety_Level": safety_level,
            "Drug_Interaction_Level": "Unknown",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "",
            "Novel_Food_Status": "To verify",
            "Reference_Count": 1,
            "Notes": notes,
            "Source_Type": "Manual text",
            "Source_Title": "",
            "Source_Organization": "",
            "Source_Year": "",
            "Source_URL": "",
        }

        final_record = normalize_source_record(raw_record)
        row_id = save_evidence_record(final_record)

        st.success(f"Evidence record saved to Supabase. Row ID: {row_id}")
        st.dataframe(pd.DataFrame([final_record]), use_container_width=True)


# =========================
# TAB 3 — PUBMED CONNECTOR
# =========================

with tab3:
    st.markdown("## PubMed Connector")
    st.caption("Search PubMed, extract evidence, standardize it, and save records to Supabase.")

    col1, col2 = st.columns(2)

    with col1:
        pubmed_plant = st.text_input(
            "Scientific name",
            value="Melissa officinalis"
        )

        pubmed_indication = st.selectbox(
            "Target indication",
            [
                "Sleep and relaxation",
                "Constipation",
                "Cough",
                "Digestive comfort",
                "Anxiety",
                "Skin inflammation",
                "IBS",
            ]
        )

    with col2:
        pubmed_dosage = st.selectbox(
            "Dosage form",
            [
                "Infusion",
                "Capsule",
                "Tablet",
                "Extract",
                "Cream",
                "Syrup",
            ]
        )

        max_results = st.slider(
            "Maximum PubMed results",
            1,
            20,
            5
        )

    if st.button("Search PubMed and save evidence", type="primary"):

        with st.spinner("Searching PubMed and saving evidence records..."):
            records = collect_pubmed_evidence(
                scientific_name=pubmed_plant,
                indication=pubmed_indication,
                dosage_form=pubmed_dosage,
                market="European Union",
                max_results=max_results,
                save=True
            )

        if not records:
            st.warning("No PubMed records were found or saved.")
        else:
            st.success(f"{len(records)} PubMed records saved to Supabase.")

            preview = []
            for r in records:
                preview.append({
                    "Row ID": r.get("row_id"),
                    "PMID": r.get("pmid"),
                    "Title": r.get("title"),
                })

            st.dataframe(pd.DataFrame(preview), use_container_width=True)


# =========================
# TAB 4 — DATABASE PREVIEW
# =========================

with tab4:
    st.markdown("## Supabase evidence database preview")

    refreshed_df = load_evidence_database()

    st.write(f"Total records: {len(refreshed_df)}")

    if refreshed_df.empty:
        st.info("No evidence records stored yet.")
    else:
        st.dataframe(refreshed_df, use_container_width=True)

        csv_db = refreshed_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download full database as CSV",
            data=csv_db,
            file_name="full_evidence_database.csv",
            mime="text/csv",
        )
