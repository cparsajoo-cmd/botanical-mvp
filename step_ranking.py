import streamlit as st
import pandas as pd
from rd_discovery_engine import build_rd_discovery_ranking


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


def render_ranking_step(inputs):
    st.markdown("---")
    st.markdown("## Step 5 — Generate unified R&D ranking")

    if st.button("Step 5: Generate unified R&D ranking", type="primary"):
        with st.spinner("Building unified R&D ranking..."):
            ranking = build_rd_discovery_ranking(
                product_type=inputs["product_type"],
                dosage_form=inputs["dosage_form"],
                indication=inputs["indication"],
                market=inputs["market"],
                target_count=inputs["target_count"],
            )

        if ranking is not None and not ranking.empty:
            ranking = ranking.copy()
            if "Rank" not in ranking.columns:
                ranking.insert(0, "Rank", range(1, len(ranking) + 1))

        st.session_state["ranking"] = ranking

    ranking = st.session_state.get("ranking")

    if ranking is None:
        return

    st.markdown("---")
    st.markdown("## Step 6 — Unified R&D Ranking")

    if ranking.empty:
        st.warning("No R&D candidates found yet.")
        return

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
        compound = row.get("compound_name", "")
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
            st.write(f"**Common name:** {row.get('Common_Name', '')}")
            st.write(f"**Region / country:** {row.get('Region', '')}")

            st.markdown("### 3. Active compound")
            st.write(f"**Compound:** {compound}")
            st.write(f"**Compound class:** {row.get('compound_class', '')}")

            st.markdown("### 4. Target and mechanism")
            st.write(f"**Major target:** {row.get('major_target', '')}")
            st.write(f"**Mechanism:** {row.get('mechanism', '')}")

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
