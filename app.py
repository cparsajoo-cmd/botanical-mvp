import streamlit as st
import pandas as pd

from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence
from report_generator import generate_report
from research_engine import run_research_engine


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Scientific decision-support system for botanical product development")


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

    return analyze_evidence(
        df=filtered,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        min_score=0,
    )


st.markdown("## 1. Product project inputs")

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
            "Anxiety",
            "Digestive comfort",
            "Constipation",
            "Cough",
            "Skin inflammation",
            "Dry mouth",
            "Allergic rhinitis",
            "IBS",
            "Wound healing",
            "Cognitive support",
            "Anti-inflammatory",
        ],
    )

with col2:
    dosage_form = st.selectbox(
        "Dosage form",
        [
            "Infusion",
            "Capsule",
            "Tablet",
            "Extract",
            "Syrup",
            "Cream",
            "Gel",
            "Mouthwash",
            "Nasal spray",
            "Chewing gum",
            "Powder",
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
            "United Kingdom",
            "Australia",
            "Iran",
            "Global",
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
    "Online results per candidate plant",
    1,
    10,
    3,
)

st.markdown("## 2. Run workflow")

st.info(
    "First collect online evidence if needed. Then generate the final botanical ranking from the database."
)

col_a, col_b = st.columns(2)

with col_a:
    collect_and_generate = st.button(
        "Step 1 — Collect online evidence and update database",
    )

with col_b:
    generate_only = st.button(
        "Step 2 — Generate final botanical ranking",
        type="primary",
    )


result = None

if collect_and_generate:
    st.markdown("## Online evidence collection")

    with st.spinner("Searching sources, extracting evidence, and saving records to Supabase..."):
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
    sources_checked = research_output.get("sources_checked", [])

    st.success(f"{len(saved_records)} online evidence records saved.")

    if candidate_plants:
        st.write("**Candidate plants searched:**")
        st.write(", ".join(candidate_plants))

    if sources_checked:
        st.write("**Sources checked:**")
        st.write(", ".join(sorted(set(sources_checked))))

    if errors:
        st.warning("Some sources returned errors.")
        st.dataframe(pd.DataFrame(errors), use_container_width=True)

    if saved_records:
        preview = []
        for r in saved_records:
            preview.append(
                {
                    "row_id": r.get("row_id"),
                    "source": r.get("source", ""),
                    "title": r.get("title", ""),
                    "compound_records_saved": r.get("compound_records_saved", 0),
                }
            )

        st.markdown("### Saved records preview")
        st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)

    st.info("Now press Step 2 to generate the final ranking from the updated database.")


if generate_only:
    df = load_evidence_database()

    result = generate_decision(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market,
        evidence_strictness=evidence_strictness,
    )


if result is not None:
    st.markdown("## 3. Final Global Botanical Ranking")

    if result.empty:
        st.warning("No evidence records found for this product question.")
    else:
        st.success(f"{len(result)} plant candidates ranked.")

        ranking_columns = [
            "Scientific_Name",
            "Common_Name",
            "Region",
            "Decision_Class",
            "Final_Score",
            "Clinical_Score",
            "Chemistry_Score",
            "Active_Compound_Score",
            "Target_Score",
            "Extraction_Score",
            "Regulatory_Score",
            "Safety_Score",
            "Novelty_Score",
            "Market_Score",
            "Commercial_Score",
            "Compound_Count",
            "Best_Compounds",
            "Best_Targets",
            "Best_Extraction_Methods",
        ]

        visible_columns = [
            c for c in ranking_columns
            if c in result.columns
        ]

        st.dataframe(
            result[visible_columns],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("## 4. Candidate details")

        score_col = "Final_Score" if "Final_Score" in result.columns else "Evidence_Score"

        for _, row in result.iterrows():
            plant_name = row.get("Scientific_Name", "")

            title = (
                f"🌿 {plant_name} — "
                f"{row.get('Decision_Class', '')} — "
                f"Final Score {row.get(score_col, '')}/100"
            )

            with st.expander(title, expanded=False):
                st.markdown("### Scores")

                score_columns = [
                    "Clinical_Score",
                    "Chemistry_Score",
                    "Active_Compound_Score",
                    "Target_Score",
                    "Extraction_Score",
                    "Regulatory_Score",
                    "Safety_Score",
                    "Novelty_Score",
                    "Market_Score",
                    "Commercial_Score",
                    "Final_Score",
                ]

                score_data = {
                    c: row.get(c, "")
                    for c in score_columns
                    if c in result.columns
                }

                st.dataframe(
                    pd.DataFrame([score_data]),
                    use_container_width=True,
                    hide_index=True,
                )

                st.markdown("### Compound intelligence")
                st.write(f"**Compound count:** {row.get('Compound_Count', '')}")
                st.write(f"**Best compounds:** {row.get('Best_Compounds', '')}")
                st.write(f"**Best targets:** {row.get('Best_Targets', '')}")
                st.write(f"**Best extraction methods:** {row.get('Best_Extraction_Methods', '')}")

                st.markdown("### Botanical and product fit")
                st.write(f"**Common name:** {row.get('Common_Name', '')}")
                st.write(f"**Region:** {row.get('Region', '')}")
                st.write(f"**Plant part:** {row.get('Plant_Part', '')}")
                st.write(f"**Extraction method:** {row.get('Extraction_Method', '')}")
                st.write(f"**Dosage form:** {row.get('Dosage_Form', '')}")
                st.write(f"**Indication:** {row.get('Target_Indication', '')}")
                st.write(f"**Market:** {row.get('Target_Market', '')}")

                st.markdown("### Regulatory and safety")
                st.write(f"**EMA:** {row.get('EMA_Status', '')}")
                st.write(f"**WHO:** {row.get('WHO_Status', '')}")
                st.write(f"**ESCOP:** {row.get('ESCOP_Status', '')}")
                st.write(f"**Regulatory evidence:** {row.get('Regulatory_Evidence', '')}")
                st.write(f"**Safety level:** {row.get('Safety_Level', '')}")
                st.write(f"**Safety signal:** {row.get('Safety_Signal', '')}")

                st.markdown("### Decision")
                st.write(row.get("Decision_Reason", ""))

                st.markdown("### Sources")
                st.write(row.get("Source_Title", ""))
                st.write(row.get("Source_URL", ""))

        st.markdown("## 5. Downloads")

        csv = result.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download final ranking as CSV",
            data=csv,
            file_name="botanical_final_ranking.csv",
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
            "Download report as TXT",
            data=report_text.encode("utf-8"),
            file_name="botanical_decision_report.txt",
            mime="text/plain",
        )


st.markdown("---")

with st.expander("Current Supabase evidence database preview"):
    refreshed_df = load_evidence_database()
    st.write(f"Total evidence records: {len(refreshed_df)}")
    st.dataframe(refreshed_df, use_container_width=True)
