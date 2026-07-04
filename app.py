import streamlit as st
import pandas as pd

from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence
from report_generator import generate_report
from research_engine import run_research_engine
from investment_decision_engine import aggregate_investment_decision
from investment_engine import build_investment_report


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Evidence-based botanical product decision support")


def generate_decision(df, product_type, dosage_form, indication, market, evidence_strictness):
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

    return result


df = load_evidence_database()

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
            "Essential oil",
        ],
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
    )

evidence_strictness = st.selectbox(
    "Evidence strictness",
    [
        "Dosage-form specific only",
        "Regulatory-first",
        "Clinical-first",
        "Flexible",
    ],
)

max_pubmed_results = st.slider(
    "Online PubMed results per candidate plant",
    1,
    10,
    3,
)

st.markdown("## Product development question")

st.info(
    f"Which medicinal plants are scientifically and commercially worth investing in "
    f"for **{product_type}** prepared as **{dosage_form}** for **{indication}** "
    f"in **{market}**?"
)

col_button_1, col_button_2 = st.columns(2)

with col_button_1:
    generate_only = st.button(
        "Generate decision from database",
        type="primary"
    )

with col_button_2:
    collect_and_generate = st.button(
        "Collect online evidence + generate decision"
    )

result = None

if collect_and_generate:
    st.markdown("## Online evidence collection")

    with st.spinner("Searching PubMed, ClinicalTrials.gov, extracting evidence, and saving records to Supabase..."):
        research_output = run_research_engine(
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            target_market=market,
            evidence_strictness=evidence_strictness,
            max_results_per_plant=max_pubmed_results,
            save=True,
        )

    saved_records = research_output.get("saved_records", [])
    errors = research_output.get("errors", [])
    candidate_plants = research_output.get("candidate_plants", [])

    st.success(f"{len(saved_records)} online evidence records saved.")

    if candidate_plants:
        st.write("**Candidate plants searched:**")
        st.write(", ".join(candidate_plants))

    if errors:
        st.warning("Some searches produced errors.")
        st.dataframe(pd.DataFrame(errors), use_container_width=True)

    if saved_records:
        st.markdown("### Saved online evidence records")
        preview = []
        for r in saved_records:
            preview.append({
                "row_id": r.get("row_id"),
                "source": r.get("source", "PubMed"),
                "pmid": r.get("pmid", ""),
                "nct_id": r.get("nct_id", ""),
                "title": r.get("title", ""),
            })
        st.dataframe(pd.DataFrame(preview), use_container_width=True)

    df = load_evidence_database()
    result = generate_decision(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        evidence_strictness=evidence_strictness,
    )

elif generate_only:
    result = generate_decision(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        evidence_strictness=evidence_strictness,
    )


if result is not None:
    st.markdown("## Decision output")

    if result.empty:
        st.warning("No evidence records found yet for this product question.")
    else:
        st.success(f"{len(result)} relevant evidence records found.")

        display_result = (
            result.sort_values("Evidence_Score", ascending=False)
            .drop_duplicates(subset=["Scientific_Name"], keep="first")
            .reset_index(drop=True)
        )

        st.info(f"{len(display_result)} unique plant candidates shown below.")

        for _, row in display_result.iterrows():
            title = (
                f"🌿 {row.get('Scientific_Name', '')} — "
                f"{row.get('Decision_Class', '')} — "
                f"Score {row.get('Evidence_Score', '')}/100"
            )

            with st.expander(title, expanded=False):
                st.write(f"**Common name:** {row.get('Common_Name', '')}")
                st.write(f"**Product type:** {row.get('Product_Type', '')}")
                st.write(f"**Dosage form:** {row.get('Dosage_Form', '')}")
                st.write(f"**Indication:** {row.get('Target_Indication', '')}")
                st.write(f"**Market:** {row.get('Target_Market', '')}")

                st.markdown("### Regulatory evidence")
                st.write(f"**EMA:** {row.get('EMA_Status', '')}")
                st.write(f"**WHO:** {row.get('WHO_Status', '')}")
                st.write(f"**ESCOP:** {row.get('ESCOP_Status', '')}")
                st.write(f"**Regulatory evidence:** {row.get('Regulatory_Evidence', '')}")

                st.markdown("### Scientific evidence")
                st.write(f"**Study type:** {row.get('Study_Type', row.get('Evidence_Type', ''))}")
                st.write(f"**Evidence type:** {row.get('Evidence_Type', '')}")
                st.write(f"**Evidence level:** {row.get('Evidence_Level', '')}")
                st.write(f"**Study model:** {row.get('Study_Model', '')}")
                st.write(f"**Evidence quality score:** {row.get('Evidence_Quality_Score', '')}")
                st.write(f"**Evidence quality class:** {row.get('Evidence_Quality_Class', '')}")
                st.write(f"**Evidence quality flags:** {row.get('Evidence_Quality_Flags', '')}")
                st.write(
                    f"**Detected dosage form:** "
                    f"{row.get('Dosage_Form_Detected', row.get('Detected_Dosage_Forms', ''))}"
                )
                st.write(
                    f"**Detected indication:** "
                    f"{row.get('Target_Indication_Detected', row.get('Detected_Indications', ''))}"
                )
                st.write(f"**Direct for selected product:** {row.get('Direct_For_Selected_Product', '')}")
                st.write(f"**Directness reason:** {row.get('Directness_Reason', '')}")

                st.markdown("### Decision")
                st.write(f"**Decision reason:** {row.get('Decision_Reason', '')}")
                st.write(f"**Safety:** {row.get('Safety_Level', '')}")
                st.write(f"**Safety signal:** {row.get('Safety_Signal', '')}")

                if row.get("Source_URL", ""):
                    st.write(f"**Source:** {row.get('Source_URL', '')}")

        st.markdown("## Final Investment Recommendation")

        investment_summary = aggregate_investment_decision(result)

        if investment_summary.empty:
            st.info("No investment recommendation available.")
        else:
            investment_columns = [
                "Scientific_Name",
                "Investment_Score",
                "Final_Decision",
                "Investment_Class",
                "Best_Evidence_Score",
                "EMA",
                "WHO",
                "ESCOP",
                "Direct_Dosage_Form_Evidence",
                "Number_of_Records",
            ]

            visible_columns = [
                c for c in investment_columns
                if c in investment_summary.columns
            ]

            st.dataframe(
                investment_summary[visible_columns],
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("## Investment Intelligence Report")

        investment_report = build_investment_report(result)

        if investment_report.empty:
            st.info("No investment intelligence report available.")
        else:
            st.dataframe(
                investment_report,
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("## Full evidence table")
        st.dataframe(result, use_container_width=True)

        csv = result.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download decision table as CSV",
            data=csv,
            file_name="botanical_decision_output.csv",
            mime="text/csv",
        )

        investment_csv = investment_report.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download investment report as CSV",
            data=investment_csv,
            file_name="botanical_investment_report.csv",
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

st.markdown("---")

with st.expander("Current Supabase evidence database preview"):
    refreshed_df = load_evidence_database()
    st.write(f"Total records: {len(refreshed_df)}")
    st.dataframe(refreshed_df, use_container_width=True)
