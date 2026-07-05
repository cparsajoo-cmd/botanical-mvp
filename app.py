import streamlit as st
import pandas as pd

from ai_discovery_engine import understand_question
from global_plant_discovery_engine import GlobalPlantDiscoveryEngine

from rd_discovery_engine import build_rd_discovery_ranking
from research_engine import run_research_engine
from compound_profile_seed import seed_compound_profiles
from evidence_database import load_evidence_database


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("AI Botanical R&D Discovery Platform")


def classify_explanation(final_class):
    if final_class == "Commercial-ready":
        return "Suitable for near-term product development."
    if final_class == "R&D candidate":
        return "Promising for R&D, but more evidence or regulatory work is needed."
    if final_class == "Discovery / high-risk candidate":
        return "High innovation potential, but high uncertainty."
    if final_class == "Early research candidate":
        return "Keep in the research pipeline."
    return "Low priority for now."


st.markdown("## Step 0 — Define R&D question")

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
            "Stress",
            "Inflammation",
            "Constipation",
            "Cough",
            "Digestive comfort",
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
            "Global R&D",
        ],
    )

target_count = st.slider(
    "Number of global plant candidates to analyze",
    10,
    100,
    50,
)

max_pubmed_results = st.slider(
    "Online PubMed results per candidate plant",
    1,
    10,
    3,
)

st.info(
    f"Find and rank global medicinal plants and active compounds for "
    f"**{product_type}** as **{dosage_form}** for **{indication}** "
    f"in **{market}**."
)


st.markdown("---")
st.markdown("## Step 1 — Understand question")

if st.button("Step 1: Understand R&D question"):
    question = understand_question(
        therapeutic_area=indication,
        dosage_form=dosage_form,
        target_market=market,
    )

    if question is None:
        st.warning("No therapeutic profile found for this indication yet.")
    else:
        st.success("Question understood.")

        st.write("**Therapeutic area:**", question.get("therapeutic_area"))
        st.write("**Dosage form:**", question.get("dosage_form"))
        st.write("**Target market:**", question.get("target_market"))

        st.write("**Targets:**")
        st.write(", ".join(question.get("targets", [])))

        st.write("**Search keywords:**")
        st.write(", ".join(question.get("keywords", [])))

        st.write("**Compound classes:**")
        st.write(", ".join(question.get("compound_classes", [])))


st.markdown("---")
st.markdown("## Step 2 — Prepare compound database")

if st.button("Step 2: Seed compound profiles"):
    saved_count = seed_compound_profiles()
    st.success(f"{saved_count} compound profiles saved.")


st.markdown("---")
st.markdown("## Step 3 — Global AI discovery test")

st.write(
    "This searches global botanical, chemical, literature, and clinical sources "
    "using the AI-understood targets and keywords."
)

if st.button("Step 3: Test global discovery engine"):
    with st.spinner("Searching global discovery sources..."):
        engine = GlobalPlantDiscoveryEngine()

        discovery_result = engine.discover(
            therapeutic_area=indication,
            dosage_form=dosage_form,
            target_market=market,
        )

    if discovery_result.get("question") is None:
        st.warning("No question profile found.")
    else:
        st.success("Global discovery completed.")

        st.write("**Sources used:**")
        st.write(", ".join(discovery_result.get("sources", [])))

        col_a, col_b, col_c, col_d = st.columns(4)

        with col_a:
            st.metric("Plants found", len(discovery_result.get("candidate_plants", [])))

        with col_b:
            st.metric("Compounds found", len(discovery_result.get("compounds", [])))

        with col_c:
            st.metric("Papers found", len(discovery_result.get("papers", [])))

        with col_d:
            st.metric("Clinical trials", len(discovery_result.get("clinical_trials", [])))

        st.markdown("### Candidate plants")
        plants_df = pd.DataFrame(discovery_result.get("candidate_plants", []))
        if plants_df.empty:
            st.info("No plants found.")
        else:
            st.dataframe(plants_df, use_container_width=True, hide_index=True)

        st.markdown("### Compounds")
        compounds_df = pd.DataFrame(discovery_result.get("compounds", []))
        if compounds_df.empty:
            st.info("No compounds found.")
        else:
            st.dataframe(compounds_df, use_container_width=True, hide_index=True)

        st.markdown("### Papers")
        papers_df = pd.DataFrame(discovery_result.get("papers", []))
        if papers_df.empty:
            st.info("No papers found.")
        else:
            st.dataframe(papers_df, use_container_width=True, hide_index=True)

        st.markdown("### Clinical trials")
        trials_df = pd.DataFrame(discovery_result.get("clinical_trials", []))
        if trials_df.empty:
            st.info("No clinical trials found.")
        else:
            st.dataframe(trials_df, use_container_width=True, hide_index=True)


st.markdown("---")
st.markdown("## Step 4 — Collect online evidence")

if st.button("Step 4: Collect online evidence"):
    with st.spinner("Searching sources and saving evidence to Supabase..."):
        research_output = run_research_engine(
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            target_market=market,
            evidence_strictness="Flexible",
            max_results_per_plant=max_pubmed_results,
            save=True,
            global_candidate_count=target_count,
        )

    saved_records = research_output.get("saved_records", [])
    errors = research_output.get("errors", [])
    sources_checked = research_output.get("sources_checked", [])
    candidate_plants = research_output.get("candidate_plants", [])

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


st.markdown("---")
st.markdown("## Step 5 — Generate unified R&D ranking")

ranking = None

if st.button("Step 5: Generate unified R&D ranking", type="primary"):
    with st.spinner("Building unified R&D ranking..."):
        ranking = build_rd_discovery_ranking(
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            market=market,
            target_count=target_count,
        )


if ranking is not None:
    st.markdown("---")
    st.markdown("## Step 6 — Unified R&D Ranking")

    if ranking.empty:
        st.warning("No R&D candidates found yet.")
    else:
        ranking = ranking.copy()
        ranking.insert(0, "Rank", range(1, len(ranking) + 1))

        st.success(f"{len(ranking)} plant–compound R&D opportunities ranked.")

        main_cols = [
            "Rank",
            "Scientific_Name",
            "Common_Name",
            "compound_name",
            "Region",
            "Final_RnD_Score",
            "Final_Class",
            "Chemistry_Score_Unified",
            "Evidence_Score_Unified",
            "Target_Match_Score",
            "Regulatory_Score_Unified",
            "Safety_Score_Unified",
            "Innovation_Score",
            "Extraction_Score_Unified",
        ]

        main_cols = [c for c in main_cols if c in ranking.columns]

        st.dataframe(
            ranking[main_cols],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("## Step 7 — Candidate profiles")

        for _, row in ranking.iterrows():
            plant = row.get("Scientific_Name", "")
            common = row.get("Common_Name", "")
            region = row.get("Region", "")
            compound = row.get("compound_name", "")
            compound_class = row.get("compound_class", "")
            target = row.get("major_target", "")
            mechanism = row.get("mechanism", "")
            final_score = row.get("Final_RnD_Score", "")
            final_class = row.get("Final_Class", "")

            title = (
                f"#{row.get('Rank')} 🌿 {plant}"
                f" — {compound if compound else 'No compound identified'}"
                f" — {final_class}"
                f" — Score {final_score}/100"
            )

            with st.expander(title, expanded=False):
                st.markdown("### 1. Executive decision")
                st.write(f"**Final class:** {final_class}")
                st.write(f"**Final R&D score:** {final_score}/100")
                st.write(f"**Interpretation:** {classify_explanation(final_class)}")

                st.markdown("### 2. Plant identity")
                st.write(f"**Scientific name:** {plant}")
                st.write(f"**Common name:** {common}")
                st.write(f"**Region / country:** {region}")

                st.markdown("### 3. Active compound")
                st.write(f"**Compound:** {compound}")
                st.write(f"**Compound class:** {compound_class}")

                st.markdown("### 4. Target and mechanism")
                st.write(f"**Major target:** {target}")
                st.write(f"**Mechanism:** {mechanism}")

                st.markdown("### 5. Extraction / formulation relevance")
                extraction_method = row.get("extraction_method", "") or row.get("Extraction_Method", "")
                st.write(f"**Extraction method:** {extraction_method}")
                st.write(f"**Plant part:** {row.get('Plant_Part', '')}")

                st.markdown("### 6. Score breakdown")

                score_cols = [
                    "Evidence_Score_Unified",
                    "Chemistry_Score_Unified",
                    "Target_Match_Score",
                    "Extraction_Score_Unified",
                    "Regulatory_Score_Unified",
                    "Safety_Score_Unified",
                    "Innovation_Score",
                    "Final_RnD_Score",
                ]

                score_data = {
                    col: row.get(col, "")
                    for col in score_cols
                    if col in ranking.columns
                }

                st.dataframe(
                    pd.DataFrame([score_data]),
                    use_container_width=True,
                    hide_index=True,
                )

                st.markdown("### 7. References")
                st.write(f"**Evidence records:** {row.get('Evidence_Record_Count', '')}")
                st.write(f"**Source titles:** {row.get('Source_Title', '')}")
                st.write(f"**Source URLs:** {row.get('Source_URL', '')}")

        st.markdown("---")
        st.markdown("## Step 8 — Download results")

        csv = ranking.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download unified R&D ranking as CSV",
            data=csv,
            file_name="unified_rd_discovery_ranking.csv",
            mime="text/csv",
        )


st.markdown("---")

with st.expander("Supabase evidence database preview"):
    df = load_evidence_database()
    st.write(f"Total evidence records: {len(df)}")
    st.dataframe(df, use_container_width=True)
