import streamlit as st
import pandas as pd
from rd_discovery_engine import build_rd_discovery_ranking


def classify_explanation(final_class):
    if final_class == "Commercial-ready":
        return "Already suitable for near-term product development or marketed-style positioning."
    if final_class == "R&D candidate":
        return "Promising for R&D, but more evidence, formulation, or regulatory work is needed."
    if final_class == "Discovery / high-risk candidate":
        return "High innovation potential, but high uncertainty."
    if final_class == "Early research candidate":
        return "Keep in the research pipeline."
    if final_class == "Low priority":
        return "Low priority for now."
    return "Needs review."


def clean_ranking(ranking):
    ranking = ranking.copy()

    if "compound_name" in ranking.columns:
        ranking["compound_name"] = (
            ranking["compound_name"]
            .astype(str)
            .str.strip()
            .str.lower()
            .str.replace("nan", "", regex=False)
        )

        ranking["compound_name"] = ranking["compound_name"].str.capitalize()

    if "Final_RnD_Score" in ranking.columns:
        ranking["Final_RnD_Score"] = pd.to_numeric(
            ranking["Final_RnD_Score"],
            errors="coerce",
        )

    duplicate_cols = [
        c for c in ["Scientific_Name", "compound_name"]
        if c in ranking.columns
    ]

    if duplicate_cols:
        ranking = ranking.drop_duplicates(subset=duplicate_cols, keep="first")

    ranking = ranking.sort_values(
        by="Final_RnD_Score",
        ascending=False,
        na_position="last",
    )

    ranking = ranking.reset_index(drop=True)
    ranking.insert(0, "Rank", range(1, len(ranking) + 1))

    return ranking


def split_ranking_sections(ranking):
    commercial = ranking[
        ranking["Final_Class"].isin(
            [
                "Commercial-ready",
                "Product-ready candidate",
                "Market-ready candidate",
            ]
        )
    ] if "Final_Class" in ranking.columns else pd.DataFrame()

    rd = ranking[
        ranking["Final_Class"].isin(
            [
                "R&D candidate",
                "Strategic development candidate",
            ]
        )
    ] if "Final_Class" in ranking.columns else pd.DataFrame()

    discovery = ranking[
        ranking["Final_Class"].isin(
            [
                "Discovery / high-risk candidate",
                "Early research candidate",
                "Low priority",
            ]
        )
    ] if "Final_Class" in ranking.columns else pd.DataFrame()

    return commercial, rd, discovery


def show_table(title, df):
    st.markdown(f"### {title}")

    if df is None or df.empty:
        st.info("No candidates in this category.")
        return

    cols = [
        "Rank",
        "Scientific_Name",
        "Common_Name",
        "compound_name",
        "Region",
        "Final_RnD_Score",
        "Final_Class",
        "Evidence_Score_Unified",
        "Chemistry_Score_Unified",
        "Target_Match_Score",
        "Regulatory_Score_Unified",
        "Safety_Score_Unified",
        "Innovation_Score",
        "Extraction_Score_Unified",
    ]

    cols = [c for c in cols if c in df.columns]

    st.dataframe(
        df[cols],
        use_container_width=True,
        hide_index=True,
    )


def render_candidate_profiles(ranking):
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

            if final_class in [
                "Commercial-ready",
                "Product-ready candidate",
                "Market-ready candidate",
            ]:
                st.success(
                    "This candidate appears suitable for commercial product positioning, subject to regulatory and formulation confirmation."
                )
            elif final_class in [
                "R&D candidate",
                "Strategic development candidate",
            ]:
                st.info(
                    "This candidate is better treated as an R&D or product-development opportunity."
                )
            else:
                st.warning(
                    "This candidate is exploratory or low-priority until stronger evidence is available."
                )

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
            ranking = clean_ranking(ranking)

        st.session_state["ranking"] = ranking

    ranking = st.session_state.get("ranking")

    if ranking is None:
        return

    st.markdown("---")
    st.markdown("## Step 6 — Unified Decision Ranking")

    if ranking.empty:
        st.warning("No candidates found yet.")
        return

    commercial, rd, discovery = split_ranking_sections(ranking)

    st.success(f"{len(ranking)} plant–compound candidates ranked.")

    st.markdown("### Summary")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Commercial / market-ready", len(commercial))

    with c2:
        st.metric("R&D opportunities", len(rd))

    with c3:
        st.metric("Discovery / low priority", len(discovery))

    show_table("A. Commercial-ready / marketed-style candidates", commercial)
    show_table("B. R&D development opportunities", rd)
    show_table("C. Discovery / exploratory / low-priority candidates", discovery)

    st.markdown("### Full ranking")
    show_table("All candidates", ranking)

    render_candidate_profiles(ranking)
