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
    """Add conservative scientific + commercial positioning layers.

    Commercial presence is indication-scoped.  A plant sold somewhere for a
    different/unknown use is NOT automatically an established product for the
    selected indication, and missing claim coverage is NOT white space.
    """
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
    if "Search_Status" not in ranking.columns:
        ranking["Search_Status"] = "SEARCH_NOT_PERFORMED"
    if "Market_Data_Usable" not in ranking.columns:
        ranking["Market_Data_Usable"] = False
    ranking["Market_Data_Usable"] = ranking["Market_Data_Usable"].fillna(False).astype(bool)

    if "Overall_Product_Hits" not in ranking.columns:
        ranking["Overall_Product_Hits"] = ranking["Product_Hits"]
    ranking["Overall_Product_Hits"] = pd.to_numeric(
        ranking["Overall_Product_Hits"], errors="coerce"
    ).fillna(0)

    if "Indication_Product_Hits" not in ranking.columns:
        # Legacy market output cannot prove that an overall product hit is for
        # the selected indication.  Fail closed rather than copying Product_Hits.
        ranking["Indication_Product_Hits"] = 0
    ranking["Indication_Product_Hits"] = pd.to_numeric(
        ranking["Indication_Product_Hits"], errors="coerce"
    ).fillna(0)

    if "Indication_Market_Search_Status" not in ranking.columns:
        # With legacy output, zero overall products after a completed search is
        # also zero indication products; positive overall products remain
        # indication-unclear unless claim-scoped data exists.
        overall_status = ranking["Search_Status"].astype(str)
        ranking["Indication_Market_Search_Status"] = "INSUFFICIENT_SAMPLE"
        zero_products = ranking["Overall_Product_Hits"] <= 0
        ranking.loc[
            zero_products & overall_status.eq("NO_PRODUCTS_FOUND"),
            "Indication_Market_Search_Status",
        ] = "NO_PRODUCTS_FOUND"
        ranking.loc[
            overall_status.isin(["SEARCH_NOT_PERFORMED", "SOURCE_UNAVAILABLE", "MARKET_NOT_COVERED", "CONNECTOR_NOT_IMPLEMENTED"]),
            "Indication_Market_Search_Status",
        ] = overall_status

    if "Chemical_Differentiation_Status" not in ranking.columns:
        ranking["Chemical_Differentiation_Status"] = ranking.get(
            "Novelty_Status", pd.Series("", index=ranking.index)
        )

    ranking["Scientific_RnD_Potential"] = (
        ranking["Evidence_Score_Unified"] * 0.30
        + ranking["Chemistry_Score_Unified"] * 0.25
        + ranking["Target_Match_Score"] * 0.20
        + ranking["Innovation_Score"] * 0.15
        + ranking["Final_RnD_Score"] * 0.10
    ).round(1)

    eligibility = ranking.get("Eligibility_Status", pd.Series("", index=ranking.index)).astype(str).str.lower()
    partition = ranking.get("Ranking_Partition", pd.Series("", index=ranking.index)).astype(str).str.lower()
    go_call = ranking.get("Go_Investigate_Hold_NoGo", pd.Series("", index=ranking.index)).astype(str).str.lower()
    ranking["Is_Hard_No_Go"] = (
        eligibility.str.startswith("no_go")
        | partition.eq("excluded_no_go")
        | go_call.eq("no_go")
    )

    ranking["Scientific_Evidence_Insufficient"] = ranking["Evidence_Score_Unified"] < 20
    overall_search_complete = ranking["Search_Status"].astype(str).isin(["COMPLETED", "NO_PRODUCTS_FOUND"])
    indication_search_complete = ranking["Indication_Market_Search_Status"].astype(str).isin(
        ["COMPLETED", "NO_PRODUCTS_FOUND"]
    )

    overall_explicit = ranking.get(
        "Commercial_Status_Overall", pd.Series("", index=ranking.index)
    ).astype(str)
    indication_explicit = ranking.get(
        "Commercial_Status_For_Indication", pd.Series("", index=ranking.index)
    ).astype(str)

    ranking["Is_Marketed_Overall"] = (
        (ranking["Overall_Product_Hits"] >= 1)
        & overall_search_complete
    ) | overall_explicit.eq("VERIFIED_MARKETED")

    ranking["Is_Marketed_For_Indication"] = (
        (ranking["Indication_Product_Hits"] >= 1)
        & indication_search_complete
    ) | indication_explicit.eq("VERIFIED_MARKETED_FOR_INDICATION")

    # Backward-compatible alias.  In an indication-specific R&D ranking,
    # "Is_Marketed" now means marketed FOR THIS indication, not merely sold for
    # any purpose.
    ranking["Is_Marketed"] = ranking["Is_Marketed_For_Indication"]

    scientific_threshold_pass = (
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

    ranking["Is_Indication_Repurposing_Opportunity"] = (
        (~ranking["Is_Hard_No_Go"])
        & (~ranking["Scientific_Evidence_Insufficient"])
        & scientific_threshold_pass
        & ranking["Is_Marketed_Overall"]
        & (~ranking["Is_Marketed_For_Indication"])
        & indication_search_complete
    )

    ranking["Is_Commercial_White_Space_Opportunity"] = (
        (~ranking["Is_Hard_No_Go"])
        & (~ranking["Scientific_Evidence_Insufficient"])
        & scientific_threshold_pass
        & (~ranking["Is_Marketed_Overall"])
        & ranking["Search_Status"].astype(str).eq("NO_PRODUCTS_FOUND")
        & indication_search_complete
    )

    ranking["Is_New_RnD_Opportunity"] = (
        ranking["Is_Indication_Repurposing_Opportunity"]
        | ranking["Is_Commercial_White_Space_Opportunity"]
    )

    def decide(row):
        if row["Is_Hard_No_Go"]:
            return "Excluded / hard no-go"
        if row["Scientific_Evidence_Insufficient"] and row["Is_Marketed_Overall"]:
            return "Commercially active / scientifically insufficient"
        if row["Scientific_Evidence_Insufficient"]:
            return "Scientifically insufficient"
        if row["Is_Marketed_For_Indication"]:
            return "Established / commercially active for indication"
        if row["Is_Indication_Repurposing_Opportunity"]:
            return "Indication-repurposing R&D opportunity"
        if row["Is_Commercial_White_Space_Opportunity"]:
            return "Commercial white-space R&D opportunity"
        if row["Is_Marketed_Overall"] and not indication_search_complete.loc[row.name]:
            return "Commercially active overall / indication unverified"
        if not overall_search_complete.loc[row.name]:
            return "Market data incomplete / scientific assessment separate"
        if not indication_search_complete.loc[row.name]:
            return "Indication market data incomplete / no novelty claim"
        return "Do not prioritize now"

    def reason(row):
        if row["Is_Hard_No_Go"]:
            return "A hard safety/regulatory gate excludes this candidate; market demand cannot override that gate."
        if row["Scientific_Evidence_Insufficient"] and row["Is_Marketed_Overall"]:
            return "Commercial presence exists, but scientific evidence is insufficient; market popularity is not efficacy evidence."
        if row["Scientific_Evidence_Insufficient"]:
            return "Scientific evidence is insufficient; market signals cannot create a validated scientific recommendation."
        if row["Is_Marketed_For_Indication"]:
            return "Verified market evidence links this plant to the selected indication; treat it as an established/commercial benchmark rather than a new botanical opportunity."
        if row["Is_Indication_Repurposing_Opportunity"]:
            return "The plant is commercially active overall, but a completed indication-scoped market assessment found no verified product for the selected indication in covered sources."
        if row["Is_Commercial_White_Space_Opportunity"]:
            return "A completed covered-source market search found no verified commercial product, while the scientific threshold for R&D prioritization is met."
        if row["Is_Marketed_Overall"]:
            return "Commercial products exist, but product claims are insufficient to determine whether the selected indication is already marketed; no repurposing/white-space claim is made."
        if not overall_search_complete.loc[row.name]:
            return "Market coverage is incomplete or unavailable; no commercial-opportunity inference is made from missing data."
        if not indication_search_complete.loc[row.name]:
            return "Overall market evidence was found, but selected-indication claim coverage is insufficient; commercial novelty remains unassessed."
        return "Current scientific and market signals do not support prioritization."

    ranking["Decision_Category"] = ranking.apply(decide, axis=1)
    ranking["Decision_Reason"] = ranking.apply(reason, axis=1)

    # Ensure the explicit commercial labels are present even for legacy rows.
    if "Commercial_Novelty_Status" not in ranking.columns:
        ranking["Commercial_Novelty_Status"] = "Commercial novelty not assessed"
    if "Commercial_Positioning" not in ranking.columns:
        ranking["Commercial_Positioning"] = ranking["Decision_Category"]

    return ranking


def split_ranking_sections(ranking):
    if "Decision_Category" not in ranking.columns:
        ranking = add_decision_layers(ranking)

    marketed_categories = {
        "Established / commercially active for indication",
        "Commercially active overall / indication unverified",
        "Commercially active / scientifically insufficient",
    }
    rd_categories = {
        "Indication-repurposing R&D opportunity",
        "Commercial white-space R&D opportunity",
    }

    marketed = ranking[ranking["Decision_Category"].isin(marketed_categories)]
    new_rd = ranking[ranking["Decision_Category"].isin(rd_categories)]
    low = ranking[~ranking["Decision_Category"].isin(marketed_categories | rd_categories)]

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
        "Commercial_Positioning",
        "Commercial_Novelty_Status",
        "Chemical_Differentiation_Status",
        "Commercial_Status_Overall",
        "Commercial_Status_For_Indication",
        "Market_Score",
        "Market_Status",
        "Overall_Product_Hits",
        "Indication_Product_Hits",
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
