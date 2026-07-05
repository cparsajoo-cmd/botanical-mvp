import streamlit as st
import pandas as pd

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
st.caption("Unified Plant–Compound–Target–Evidence R&D Decision Engine")


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
st.markdown("## Step 1 — Prepare compound database")

st.write(
    "Click this only once, or when you want to refresh the internal compound profile database."
)

if st.button("Step 1: Seed compound profiles"):
    saved_count = seed_compound_profiles()
    st.success(f"{saved_count} compound profiles saved.")


st.markdown("---")
st.markdown("## Step 2 — Collect online evidence")

st.write(
    "This searches online scientific and regulatory sources, extracts evidence, compounds, targets, and saves them to Supabase."
)

collect_done = False

if st.button("Step 2: Collect online evidence"):
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

    collect_done = True


st.markdown("---")
st.markdown("## Step 3 — Generate unified R&D ranking")

st.write(
    "This combines plants, compounds, targets, evidence, extraction, regulation, safety, and innovation into one ranking."
)

ranking = None

if st.button("Step 3: Generate unified R&D ranking", type="primary"):
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
    st.markdown("## Step 4 — Unified R&D Ranking")

    if ranking.empty:
        st.warning("No R&D candidates found yet.")
    else:
        st.success(f"{len(ranking)} plant–compound R&D opportunities ranked.")

        top_view_cols = [
            "Scientific_Name",
            "Common_Name",
            "Region",
            "compound_name",
            "compound_class",
            "major_target",
            "Evidence_Record_Count",
            "Evidence_Score_Unified",
            "Chemistry_Score_Unified",
            "Target_Match_Score",
            "Extraction_Score_Unified",
            "Regulatory_Score_Unified",
            "Safety_Score_Unified",
            "Innovation_Score",
            "Final_RnD_Score",
            "Final_Class",
        ]

        top_view_cols = [c for c in top_view_cols if c in ranking.columns]

        st.dataframe(
            ranking[top_view_cols],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("## Step 5 — Candidate profiles")

        for _, row in ranking.iterrows():
            plant = row.get("Scientific_Name", "")
            compound = row.get("compound_name", "")
            final_score = row.get("Final_RnD_Score", "")
            final_class = row.get("Final_Class", "")

            title = (
                f"🌿 {plant}"
                f" — {compound if compound else 'No compound identified'}"
                f" — {final_class}"
                f" — Score {final_score}/100"
            )

            with st.expander(title, expanded=False):
                st.markdown("### 1. Identity")
                st.write(f"**Scientific name:** {plant}")
                st.write(f"**Common name:** {row.get('Common_Name', '')}")
                st.write(f"**Region / country:** {row.get('Region', '')}")

                st.markdown("### 2. Active compound")
                st.write(f"**Compound:** {compound}")
                st.write(f"**Compound class:** {row.get('compound_class', '')}")

                st.markdown("### 3. Target and mechanism")
                st.write(f"**Major target:** {row.get('major_target', '')}")
                st.write(f"**Mechanism:** {row.get('mechanism', '')}")

                st.markdown("### 4. Extraction")
                extraction_method = row.get("extraction_method", "") or row.get("Extraction_Method", "")
                st.write(f"**Extraction method:** {extraction_method}")
                st.write(f"**Plant part:** {row.get('Plant_Part', '')}")

                st.markdown("### 5. Scores")
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

                st.markdown("### 6. Decision interpretation")

                if final_class == "Commercial-ready":
                    st.success(
                        "Commercial-ready: suitable for near-term product development."
                    )
                elif final_class == "R&D candidate":
                    st.info(
                        "R&D candidate: promising chemistry or target profile, but more evidence or regulatory work is needed."
                    )
                elif final_class == "Discovery / high-risk candidate":
                    st.warning(
                        "Discovery candidate: high innovation potential, but high scientific or regulatory uncertainty."
                    )
                elif final_class == "Early research candidate":
                    st.info(
                        "Early research candidate: keep in pipeline, but not ready for product development."
                    )
                else:
                    st.warning("Low priority for now.")

                st.markdown("### 7. References")
                st.write(f"**Evidence records:** {row.get('Evidence_Record_Count', '')}")
                st.write(f"**Source titles:** {row.get('Source_Title', '')}")
                st.write(f"**Source URLs:** {row.get('Source_URL', '')}")

        st.markdown("---")
        st.markdown("## Step 6 — Download results")

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
