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
from global_candidate_ranking_engine import rank_global_candidates
from plant_compound_ranking_engine import build_plant_compound_ranking
from compound_profile_seed import seed_compound_profiles


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Plant → Active Compound → Target → Evidence → R&D Decision")


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
    f"Which medicinal plants and active compounds are worth investigating for "
    f"**{product_type}** prepared as **{dosage_form}** for **{indication}** "
    f"in **{market}**?"
)

st.markdown("## Compound profile database")

if st.button("Seed compound profiles"):
    saved_count = seed_compound_profiles()
    st.success(f"{saved_count} compound profiles saved.")

st.markdown("## Global plant candidate ranking")

target_count = st.slider(
    "Number of global plant candidates to rank",
    10,
    100,
    50,
)

show_global_ranking = st.button("Rank global plant candidates")

global_ranking = None

if show_global_ranking:
    global_ranking = rank_global_candidates(
        indication=indication,
        dosage_form=dosage_form,
        market=market,
        target_count=target_count,
    )

    if global_ranking.empty:
        st.warning("No global plant candidates found for this indication.")
    else:
        st.success(f"{len(global_ranking)} global plant candidates ranked.")

        st.dataframe(
            global_ranking,
            use_container_width=True,
            hide_index=True,
        )

        global_csv = global_ranking.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download global plant ranking as CSV",
            data=global_csv,
            file_name="global_plant_candidate_ranking.csv",
            mime="text/csv",
        )


st.markdown("## Active compound / target ranking")

show_compound_ranking = st.button("Rank active compounds and targets")

if show_compound_ranking:
    if global_ranking is None:
        global_ranking = rank_global_candidates(
            indication=indication,
            dosage_form=dosage_form,
            market=market,
            target_count=target_count,
        )

    selected_plants = []
    if global_ranking is not None and not global_ranking.empty:
        selected_plants = global_ranking["Scientific_Name"].dropna().astype(str).tolist()

    compound_ranking = build_plant_compound_ranking(
        indication=indication,
        selected_plants=selected_plants,
    )

    if compound_ranking.empty:
        st.warning("No compound candidates found.")
    else:
        st.success(f"{len(compound_ranking)} plant-compound-target candidates ranked.")

        st.dataframe(
            compound_ranking,
            use_container_width=True,
            hide_index=True,
        )

        compound_csv = compound_ranking.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download compound ranking as CSV",
            data=compound_csv,
            file_name="plant_compound_target_ranking.csv",
            mime="text/csv",
        )


st.markdown("## Evidence collection and decision")

col_button_1, col_button_2 = st.columns(2)

with col_button_1:
    generate_only = st.button(
        "Generate decision from database",
        type="primary",
    )

with col_button_2:
    collect_and_generate = st.button(
        "Collect online evidence + generate decision"
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

    if sources_checked:
        st.write("**Sources checked:**")
        st.write(", ".join(sorted(set(sources_checked))))

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
            preview.append(
                {
                    "row_id": r.get("row_id"),
                    "source": r.get("source", "Unknown"),
                    "pmid": r.get("pmid", ""),
                    "nct_id": r.get("nct_id", ""),
                    "title": r.get("title", ""),
                    "compound_records_saved": r.get("compound_records_saved", 0),
                }
            )
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

        score_col = "Final_Score" if "Final_Score" in result.columns else "Evidence_Score"

        display_result = (
            result.sort_values(score_col, ascending=False)
            .drop_duplicates(subset=["Scientific_Name"], keep="first")
            .reset_index(drop=True)
        )

        st.info(f"{len(display_result)} unique plant candidates shown below.")

        for _, row in display_result.iterrows():
            plant_name = row.get("Scientific_Name", "")

            title = (
                f"🌿 {plant_name} — "
                f"{row.get('Decision_Class', '')} — "
                f"Final Score {row.get(score_col, '')}/100"
            )

            with st.expander(title, expanded=False):
                st.write(f"**Common name:** {row.get('Common_Name', '')}")
                st.write(f"**Region:** {row.get('Region', '')}")
                st.write(f"**Product type:** {row.get('Product_Type', '')}")
                st.write(f"**Dosage form:** {row.get('Dosage_Form', '')}")
                st.write(f"**Indication:** {row.get('Target_Indication', '')}")
                st.write(f"**Market:** {row.get('Target_Market', '')}")

                st.markdown("### Multi-criteria decision scores")
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

                if score_data:
                    st.dataframe(
                        pd.DataFrame([score_data]),
                        use_container_width=True,
                        hide_index=True,
                    )

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

                st.markdown("### Chemistry / Active compound intelligence")
                st.write(f"**Known active compounds:** {row.get('Known_Active_Compounds', '')}")
                st.write(f"**Detected active compounds:** {row.get('Active_Compounds', '')}")
                st.write(f"**Known targets:** {row.get('Known_Targets', '')}")
                st.write(f"**Detected molecular targets:** {row.get('Molecular_Targets', '')}")
                st.write(f"**Plant part:** {row.get('Plant_Part', '')}")
                st.write(f"**Extraction method:** {row.get('Extraction_Method', '')}")
                st.write(f"**Chemistry score:** {row.get('Chemistry_Score', '')}")

                st.markdown("### Plant-compound-target candidates")

                compound_for_plant = build_plant_compound_ranking(
                    indication=indication,
                    selected_plants=[plant_name],
                )

                if compound_for_plant.empty:
                    st.write("No compound-target candidates available for this plant.")
                else:
                    st.dataframe(
                        compound_for_plant,
                        use_container_width=True,
                        hide_index=True,
                    )

                st.markdown("### Decision")
                st.write(f"**Decision reason:** {row.get('Decision_Reason', '')}")
                st.write(f"**Safety:** {row.get('Safety_Level', '')}")
                st.write(f"**Safety signal:** {row.get('Safety_Signal', '')}")

                st.markdown("### Sources / References")

                plant_sources = result[
                    result["Scientific_Name"] == plant_name
                ].copy()

                if not plant_sources.empty:
                    source_cols = [
                        "Source_Type",
                        "Source_Title",
                        "Source_URL",
                        "Source_Organization",
                        "Source_Year",
                    ]

                    available_cols = [
                        c for c in source_cols
                        if c in plant_sources.columns
                    ]

                    if available_cols:
                        refs = (
                            plant_sources[available_cols]
                            .drop_duplicates()
                            .reset_index(drop=True)
                        )

                        st.dataframe(
                            refs,
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.write("No reference columns available.")
                else:
                    st.write("No references available.")

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
