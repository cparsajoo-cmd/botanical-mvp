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


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)


def load_data():
    return load_evidence_database()


df = load_data()

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Evidence-based botanical product decision support")

tab1, tab2, tab3 = st.tabs(
    [
        "1. Product Decision",
        "2. Source Ingestion",
        "3. Database Preview",
    ]
)

# =========================================================
# TAB 1 — PRODUCT DECISION
# =========================================================

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
            ],
            key="decision_product_type",
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
            ],
            key="decision_indication",
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
            ],
            key="decision_dosage_form",
        )

        market = st.selectbox(
            "Target market",
            [
                "European Union",
                "France",
                "United States",
                "Canada",
                "Iran",
            ],
            key="decision_market",
        )

    evidence_strictness = st.selectbox(
        "Evidence strictness",
        [
            "Dosage-form specific only",
            "Regulatory-first",
            "Clinical-first",
            "Flexible",
        ],
        key="decision_evidence_strictness",
    )

    st.markdown("## Product development question")

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
            st.info(
                "This means the platform is structurally ready, but the knowledge database "
                "does not yet contain evidence records for this exact combination."
            )

        else:
            st.success(str(len(result)) + " relevant plant records found.")

            priority = result[result["Decision_Class"] == "Priority candidate"]
            conditional = result[result["Decision_Class"] == "Conditional candidate"]
            supportive = result[result["Decision_Class"] == "Supportive candidate"]
            gaps = result[result["Decision_Class"] == "Evidence gap"]

            if not priority.empty:
                st.markdown("## Priority candidates")
                for _, row in priority.iterrows():
                    with st.expander(f"🌿 {row.get('Scientific_Name', '')} — Score {row.get('Evidence_Score', '')}/100", expanded=True):
                        st.write(f"**Common name:** {row.get('Common_Name', '')}")
                        st.write(f"**Decision:** {row.get('Decision_Class', '')}")
                        st.write(f"**Evidence filter status:** {row.get('Evidence_Filter_Status', '')}")
                        st.write(f"**Evidence filter reason:** {row.get('Evidence_Filter_Reason', '')}")
                        st.write(f"**EMA:** {row.get('EMA_Status', '')}")
                        st.write(f"**WHO:** {row.get('WHO_Status', '')}")
                        st.write(f"**ESCOP:** {row.get('ESCOP_Status', '')}")
                        st.write(f"**Clinical level:** {row.get('Clinical_Level', '')}")
                        st.write(f"**Dosage-form evidence:** {row.get('Infusion_Evidence', '')}")
                        st.write(f"**Safety:** {row.get('Safety_Level', '')}")
                        st.write(f"**Reason / notes:** {row.get('Notes', '')}")

            if not conditional.empty:
                st.markdown("## Conditional candidates")
                for _, row in conditional.iterrows():
                    with st.expander(f"🌱 {row.get('Scientific_Name', '')} — Score {row.get('Evidence_Score', '')}/100"):
                        st.write(f"**Decision:** {row.get('Decision_Class', '')}")
                        st.write(f"**Evidence filter status:** {row.get('Evidence_Filter_Status', '')}")
                        st.write(f"**Evidence filter reason:** {row.get('Evidence_Filter_Reason', '')}")
                        st.write(f"**Reason / notes:** {row.get('Notes', '')}")

            if not supportive.empty:
                st.markdown("## Supportive candidates")
                for _, row in supportive.iterrows():
                    with st.expander(f"🍃 {row.get('Scientific_Name', '')} — Score {row.get('Evidence_Score', '')}/100"):
                        st.write(f"**Decision:** {row.get('Decision_Class', '')}")
                        st.write(f"**Evidence filter status:** {row.get('Evidence_Filter_Status', '')}")
                        st.write(f"**Evidence filter reason:** {row.get('Evidence_Filter_Reason', '')}")
                        st.write(f"**Reason / notes:** {row.get('Notes', '')}")

            if not gaps.empty:
                st.markdown("## Evidence gaps")
                for _, row in gaps.iterrows():
                    with st.expander(f"⚠️ {row.get('Scientific_Name', '')} — Evidence gap"):
                        st.write(f"**Score:** {row.get('Evidence_Score', '')}/100")
                        st.write(f"**Evidence filter status:** {row.get('Evidence_Filter_Status', '')}")
                        st.write(f"**Evidence filter reason:** {row.get('Evidence_Filter_Reason', '')}")
                        st.write(f"**Gap / notes:** {row.get('Notes', '')}")

            st.markdown("## Full evidence table")
            st.dataframe(result, use_container_width=True)

            csv = result.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="Download decision table as CSV",
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
                label="Download decision report as TXT",
                data=report_text.encode("utf-8"),
                file_name="botanical_decision_report.txt",
                mime="text/plain",
            )


# =========================================================
# TAB 2 — SOURCE INGESTION
# =========================================================

with tab2:

    st.markdown("## Source ingestion")
    st.caption("Paste scientific source text, extract fields, edit them, and save the record to the database.")

    source_text = st.text_area(
        "Paste source text",
        height=250,
        placeholder="Paste text from EMA, WHO, ESCOP, PubMed abstract, monograph, or report...",
        key="source_text_area",
    )

    if st.button("Extract fields from source text", type="primary"):
        if not source_text.strip():
            st.warning("Please paste source text first.")
        else:
            extracted = extract_evidence_from_text(source_text)
            st.session_state["extracted_record"] = extracted
            st.success("Fields extracted. Review and edit below.")

    record = st.session_state.get("extracted_record", {})

    st.markdown("## Review extracted record")

    with st.form("source_ingestion_form"):

        col1, col2 = st.columns(2)

        with col1:
            scientific_name = st.text_input(
                "Scientific name",
                value=record.get("Scientific_Name", ""),
            )

            common_name = st.text_input(
                "Common name",
                value=record.get("Common_Name", ""),
            )

            product_type_ing = st.selectbox(
                "Product type",
                [
                    "Herbal product",
                    "Food supplement",
                    "Cosmetic",
                    "Medical device",
                    "Veterinary botanical product",
                ],
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

            dosage_form_ing = st.selectbox(
                "Dosage form",
                dosage_options,
                index=dosage_index,
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
                index=indication_index,
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
                index=market_index,
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
                ],
            )

            source_title = st.text_input("Source title")
            source_organization = st.text_input("Source organization")
            source_year = st.text_input("Source year")
            source_url = st.text_input("Source URL / DOI")

            status_options = ["", "Yes", "No", "To verify"]

            ema_value = record.get("EMA_Status", "")
            ema_index = status_options.index(ema_value) if ema_value in status_options else 0

            ema_status = st.selectbox("EMA status", status_options, index=ema_index)

            who_value = record.get("WHO_Status", "")
            who_index = status_options.index(who_value) if who_value in status_options else 0

            who_status = st.selectbox("WHO status", status_options, index=who_index)

            escop_value = record.get("ESCOP_Status", "")
            escop_index = status_options.index(escop_value) if escop_value in status_options else 0

            escop_status = st.selectbox("ESCOP status", status_options, index=escop_index)

        st.markdown("## Evidence assessment")

        col3, col4 = st.columns(2)

        with col3:
            clinical_options = ["", "Strong", "Moderate", "Weak", "Not found"]

            clinical_value = record.get("Clinical_Level", "")
            clinical_index = clinical_options.index(clinical_value) if clinical_value in clinical_options else 0

            clinical_level = st.selectbox(
                "Clinical level",
                clinical_options,
                index=clinical_index,
            )

            clinical_rct_count = st.number_input(
                "Clinical RCT count",
                min_value=0,
                step=1,
                value=int(record.get("Clinical_RCT_Count", 0) or 0),
            )

            meta_options = ["", "Strong", "Moderate", "Weak", "Not found"]

            meta_value = record.get("Meta_Level", "")
            meta_index = meta_options.index(meta_value) if meta_value in meta_options else 0

            meta_level = st.selectbox(
                "Meta-analysis level",
                meta_options,
                index=meta_index,
            )

            meta_count = st.number_input(
                "Meta-analysis count",
                min_value=0,
                step=1,
                value=int(record.get("Meta_Count", 0) or 0),
            )

        with col4:
            dosage_evidence_options = ["", "Direct", "Indirect", "Not found"]

            infusion_value = record.get("Infusion_Evidence", "")
            infusion_index = dosage_evidence_options.index(infusion_value) if infusion_value in dosage_evidence_options else 0

            infusion_evidence = st.selectbox(
                "Dosage-form specific evidence",
                dosage_evidence_options,
                index=infusion_index,
            )

            safety_options = ["", "Good", "Acceptable", "Caution", "High risk", "Unknown"]

            safety_value = record.get("Safety_Level", "")
            safety_index = safety_options.index(safety_value) if safety_value in safety_options else 0

            safety_level = st.selectbox(
                "Safety level",
                safety_options,
                index=safety_index,
            )

            drug_interaction_level = st.selectbox(
                "Drug interaction level",
                ["", "Low", "Moderate", "High", "Unknown"],
            )

            commercial_level = st.selectbox(
                "Commercial level",
                ["", "High", "Medium", "Low", "Unknown"],
            )

        regulatory_status = st.text_input(
            "Regulatory status",
            value=record.get("Regulatory_Status", ""),
        )

        novel_food_status = st.selectbox(
            "Novel food status",
            ["", "No", "Yes", "To verify"],
        )

        notes = st.text_area(
            "Notes / extracted evidence",
            value=record.get("Notes", ""),
            height=200,
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
                "Product_Type": product_type_ing,
                "Dosage_Form": dosage_form_ing,
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


# =========================================================
# TAB 3 — DATABASE PREVIEW
# =========================================================

with tab3:

    st.markdown("## Evidence database preview")
    st.caption("This table shows the current evidence records available to the decision engine.")

    refreshed_df = load_evidence_database()

    st.write(f"Total records: {len(refreshed_df)}")
    st.dataframe(refreshed_df, use_container_width=True)

    csv_db = refreshed_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download full database as CSV",
        data=csv_db,
        file_name="full_evidence_database.csv",
        mime="text/csv",
    )
