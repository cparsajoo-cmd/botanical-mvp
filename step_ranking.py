import streamlit as st
import pandas as pd

from rd_discovery_engine import build_rd_discovery_ranking
from market_intelligence_engine import MarketIntelligenceEngine


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

    score_cols = [
        "Final_RnD_Score",
        "Evidence_Score_Unified",
        "Chemistry_Score_Unified",
        "Target_Match_Score",
        "Regulatory_Score_Unified",
        "Safety_Score_Unified",
        "Innovation_Score",
        "Extraction_Score_Unified",
    ]

    for col in score_cols:
        if col in ranking.columns:
            ranking[col] = pd.to_numeric(ranking[col], errors="coerce").fillna(0)
        else:
            ranking[col] = 0

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

    if "Rank" in ranking.columns:
        ranking = ranking.drop(columns=["Rank"])

    ranking.insert(0, "Rank", range(1, len(ranking) + 1))

    return ranking


def attach_market_intelligence(ranking, inputs):
    ranking = ranking.copy()
    engine = MarketIntelligenceEngine()

    market_rows = []

    for _, row in ranking.iterrows():
        try:
            result = engine.evaluate(
                row=row,
                indication=inputs.get("indication", ""),
                dosage_form=inputs.get("dosage_form", ""),
                market=inputs.get("market", ""),
            )
        except Exception:
            result = {
                "Market_Score": 0,
                "Market_Status": "Market analysis error",
                "Product_Hits": 0,
                "Regulatory_Hits": 0,
                "Patent_Hits": 0,
                "White_Space": "Unknown",
                "Search_Status": "SOURCE_UNAVAILABLE",
                "Market_Data_Usable": False,
                "Market_Score_Breakdown": {},
            }

        market_rows.append(result)

    market_df = pd.DataFrame(market_rows)

    ranking = pd.concat(
        [ranking.reset_index(drop=True), market_df.reset_index(drop=True)],
        axis=1,
    )

    for col in ["Market_Score", "Product_Hits", "Regulatory_Hits", "Patent_Hits"]:
        if col not in ranking.columns:
            ranking[col] = 0
        ranking[col] = pd.to_numeric(ranking[col], errors="coerce").fillna(0)

    if "Market_Status" not in ranking.columns:
        ranking["Market_Status"] = "No market signal yet"

    if "White_Space" not in ranking.columns:
        ranking["White_Space"] = "Unknown"
    if "Search_Status" not in ranking.columns:
        ranking["Search_Status"] = "SEARCH_NOT_PERFORMED"
    if "Market_Data_Usable" not in ranking.columns:
        ranking["Market_Data_Usable"] = False
    ranking["Market_Data_Usable"] = ranking["Market_Data_Usable"].fillna(False).astype(bool)

    return ranking


def add_decision_layers(ranking):
    ranking = ranking.copy()

    needed_scores = [
        "Final_RnD_Score",
        "Evidence_Score_Unified",
        "Chemistry_Score_Unified",
        "Target_Match_Score",
        "Innovation_Score",
        "Market_Score",
        "Product_Hits",
        "Regulatory_Hits",
        "Patent_Hits",
    ]

    for col in needed_scores:
        if col not in ranking.columns:
            ranking[col] = 0
        ranking[col] = pd.to_numeric(ranking[col], errors="coerce").fillna(0)

    if "Market_Status" not in ranking.columns:
        ranking["Market_Status"] = "No market signal yet"

    ranking["Scientific_RnD_Potential"] = (
        ranking["Evidence_Score_Unified"] * 0.30
        + ranking["Chemistry_Score_Unified"] * 0.25
        + ranking["Target_Match_Score"] * 0.20
        + ranking["Innovation_Score"] * 0.15
        + ranking["Final_RnD_Score"] * 0.10
    ).round(1)

    # Phase 8: only market evidence may establish commercial presence.
    # Regulatory_Hits is retained as a compatibility column but is never
    # consulted here. Missing/unavailable market data is also not white space.
    if "Search_Status" not in ranking.columns:
        ranking["Search_Status"] = "SEARCH_NOT_PERFORMED"
    if "Market_Data_Usable" not in ranking.columns:
        ranking["Market_Data_Usable"] = False

    ranking["Is_Marketed"] = (
        (ranking["Market_Data_Usable"].astype(bool))
        & (
            (ranking["Product_Hits"] >= 1)
            | ranking["Market_Status"].astype(str).str.contains(
                "Market evidence available|verified marketed product", case=False, na=False
            )
        )
    )

    eligibility = ranking.get("Eligibility_Status", pd.Series("", index=ranking.index)).astype(str).str.lower()
    partition = ranking.get("Ranking_Partition", pd.Series("", index=ranking.index)).astype(str).str.lower()
    go_call = ranking.get("Go_Investigate_Hold_NoGo", pd.Series("", index=ranking.index)).astype(str).str.lower()
    ranking["Is_Hard_No_Go"] = (
        eligibility.str.startswith("no_go")
        | partition.eq("excluded_no_go")
        | go_call.eq("no_go")
    )

    ranking["Scientific_Evidence_Insufficient"] = ranking["Evidence_Score_Unified"] < 20
    market_search_complete = ranking["Search_Status"].astype(str).isin(["COMPLETED", "NO_PRODUCTS_FOUND"])

    ranking["Is_New_RnD_Opportunity"] = (
        (~ranking["Is_Hard_No_Go"])
        & (~ranking["Scientific_Evidence_Insufficient"])
        & (~ranking["Is_Marketed"])
        & market_search_complete
        & (
            (ranking["Scientific_RnD_Potential"] >= 40)
            | (ranking["Final_RnD_Score"] >= 50)
            | (
                (ranking["Chemistry_Score_Unified"] >= 50)
                & (ranking["Evidence_Score_Unified"] >= 20)
            )
            | (
                (ranking["Target_Match_Score"] >= 50)
                & (ranking["Chemistry_Score_Unified"] >= 40)
            )
        )
    )

    def decide(row):
        if row["Is_Hard_No_Go"]:
            return "Excluded / hard no-go"
        if row["Scientific_Evidence_Insufficient"] and row["Is_Marketed"]:
            return "Commercially interesting / scientifically insufficient"
        if row["Scientific_Evidence_Insufficient"]:
            return "Scientifically insufficient"
        if row["Is_Marketed"]:
            return "Scientifically supported / commercially active"
        if row["Is_New_RnD_Opportunity"]:
            return "New R&D / white-space opportunity"
        if not market_search_complete.loc[row.name]:
            return "Market data incomplete / scientific assessment separate"
        return "Do not prioritize now"

    def reason(row):
        if row["Is_Hard_No_Go"]:
            return "A hard safety/regulatory gate excludes this candidate; market demand cannot override that gate."
        if row["Scientific_Evidence_Insufficient"] and row["Is_Marketed"]:
            return "Commercial presence exists, but scientific evidence is insufficient; market popularity is not efficacy evidence."
        if row["Scientific_Evidence_Insufficient"]:
            return "Scientific evidence is insufficient; market signals cannot create a validated scientific recommendation."
        if row["Is_Marketed"]:
            return "Scientific support and commercial presence are both present and are reported as separate dimensions."
        if row["Is_New_RnD_Opportunity"]:
            return "Scientific support is present and a completed market search indicates limited verified commercial presence."
        if row.get("Search_Status") not in ("COMPLETED", "NO_PRODUCTS_FOUND"):
            return "Market coverage is incomplete or unavailable; no commercial-opportunity inference is made from missing data."
        return "Current scientific and market signals do not support prioritization."

    ranking["Decision_Category"] = ranking.apply(decide, axis=1)
    ranking["Decision_Reason"] = ranking.apply(reason, axis=1)

    return ranking


def split_ranking_sections(ranking):
    if "Decision_Category" not in ranking.columns:
        ranking = add_decision_layers(ranking)

    marketed = ranking[
        ranking["Decision_Category"] == "Already marketed / commercial candidate"
    ]

    new_rd = ranking[
        ranking["Decision_Category"] == "New R&D / white-space opportunity"
    ]

    low = ranking[
        ranking["Decision_Category"] == "Do not prioritize now"
    ]

    return marketed, new_rd, low


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
        "Decision_Category",
        "Decision_Reason",
        "Market_Score",
        "Market_Status",
        "Product_Hits",
        "Regulatory_Hits",
        "Patent_Hits",
        "White_Space",
        "Scientific_RnD_Potential",
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
        decision_category = row.get("Decision_Category", "")
        market_status = row.get("Market_Status", "")

        title = (
            f"#{row.get('Rank')} 🌿 {plant}"
            f" — {compound if compound else 'No compound identified'}"
            f" — {decision_category}"
            f" — R&D Score {final_score}/100"
        )

        with st.expander(title, expanded=False):
            st.markdown("### 1. Executive decision")
            st.write(f"**Decision category:** {decision_category}")
            st.write(f"**Decision reason:** {row.get('Decision_Reason', '')}")
            st.write(f"**Scientific/R&D class:** {row.get('Final_Class', '')}")
            st.write(f"**R&D score:** {final_score}/100")
            st.write(f"**Scientific R&D potential:** {row.get('Scientific_RnD_Potential', '')}/100")
            st.write(f"**Market status:** {market_status}")
            st.write(f"**Market score:** {row.get('Market_Score', '')}/100")
            st.write(f"**White space:** {row.get('White_Space', '')}")

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

            st.markdown("### 5. Market evidence")
            st.write(f"**Product hits:** {row.get('Product_Hits', '')}")
            st.write(f"**Regulatory hits:** {row.get('Regulatory_Hits', '')}")
            st.write(f"**Patent hits:** {row.get('Patent_Hits', '')}")

            st.markdown("### 6. Extraction / formulation relevance")
            extraction_method = row.get("extraction_method", "") or row.get("Extraction_Method", "")
            st.write(f"**Extraction method:** {extraction_method}")
            st.write(f"**Plant part:** {row.get('Plant_Part', '')}")

            st.markdown("### 7. Score breakdown")

            score_cols = [
                "Market_Score",
                "Scientific_RnD_Potential",
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

            st.markdown("### 8. References")
            st.write(f"**Evidence records:** {row.get('Evidence_Record_Count', '')}")
            st.write(f"**Source titles:** {row.get('Source_Title', '')}")
            st.write(f"**Source URLs:** {row.get('Source_URL', '')}")


def render_ranking_step(inputs):
    st.markdown("---")
    st.markdown("## Step 5 — Generate unified market + R&D ranking")

    if st.button("Step 5: Generate unified market + R&D ranking", type="primary"):
        with st.spinner("Building unified market + R&D ranking..."):
            ranking = build_rd_discovery_ranking(
                product_type=inputs["product_type"],
                dosage_form=inputs["dosage_form"],
                indication=inputs["indication"],
                market=inputs["market"],
                target_count=inputs["target_count"],
            )

        if ranking is not None and not ranking.empty:
            ranking = clean_ranking(ranking)
            ranking = attach_market_intelligence(ranking, inputs)
            ranking = add_decision_layers(ranking)

        st.session_state["ranking"] = ranking

    ranking = st.session_state.get("ranking")

    if ranking is None:
        return

    if ranking.empty:
        st.warning("No candidates found yet.")
        return

    if "Decision_Category" not in ranking.columns:
        ranking = clean_ranking(ranking)
        ranking = attach_market_intelligence(ranking, inputs)
        ranking = add_decision_layers(ranking)
        st.session_state["ranking"] = ranking

    st.markdown("---")
    st.markdown("## Step 6 — Unified Market + R&D Decision Ranking")

    marketed, new_rd, low = split_ranking_sections(ranking)

    st.success(f"{len(ranking)} plant–compound candidates ranked.")

    st.markdown("### Summary")
    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Already marketed / commercial", len(marketed))

    with c2:
        st.metric("New R&D / white-space", len(new_rd))

    with c3:
        st.metric("Do not prioritize", len(low))

    show_table("A. Already marketed / commercial candidates", marketed)
    show_table("B. New R&D / white-space opportunities", new_rd)
    show_table("C. Do not prioritize / low-priority candidates", low)

    st.markdown("### Full ranking")
    show_table("All candidates", ranking)

    render_candidate_profiles(ranking)
