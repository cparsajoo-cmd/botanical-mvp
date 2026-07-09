import pandas as pd
import streamlit as st

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def _safe_unique(series):
    if series is None:
        return []
    return [x for x in series.dropna().astype(str).unique().tolist() if x.strip()]


def _market_notice(landscape_df):
    if landscape_df is None or landscape_df.empty:
        return

    if "Patent_Search_Status" in landscape_df.columns:
        if (landscape_df["Patent_Search_Status"] == "Not configured").all():
            st.caption(
                "Patent search is not configured yet. This is not a scientific error; "
                "it only means EPO_OPS_KEY / EPO_OPS_SECRET are missing."
            )

    if "Retail_Products_Status" in landscape_df.columns:
        if (landscape_df["Retail_Products_Status"] == "Not configured").all():
            st.caption(
                "Retail/brand product scanning is not configured yet. Add a search API "
                "key later if you want automated retail monitoring."
            )


def _build_decision_summary(result_df, landscape_df=None):
    if result_df is None or result_df.empty:
        return pd.DataFrame()

    group_cols = ["Alternative_Plant"]
    agg = {
        "R&D_Opportunity_Score": "max",
        "Decision_Class": lambda x: "; ".join(sorted(set(x.dropna().astype(str))))[:200],
        "Reference_Plant": lambda x: ", ".join(sorted(set(x.dropna().astype(str))))[:250],
        "Shared_or_Similar_Compound": lambda x: ", ".join(sorted(set(x.dropna().astype(str))))[:250],
        "Target_or_Mechanism": lambda x: ", ".join(sorted(set(x.dropna().astype(str))))[:250],
        "Safety_Flags": lambda x: ", ".join(sorted(set(x.dropna().astype(str))))[:250],
        "Rationale": lambda x: " | ".join(sorted(set(x.dropna().astype(str))))[:500],
    }

    available_agg = {k: v for k, v in agg.items() if k in result_df.columns}
    summary = result_df.groupby(group_cols, as_index=False).agg(available_agg)

    summary = summary.rename(
        columns={
            "Alternative_Plant": "Candidate_Plant",
            "R&D_Opportunity_Score": "Best_R&D_Score",
            "Reference_Plant": "Compared_Against",
            "Shared_or_Similar_Compound": "Key_Compounds",
            "Target_or_Mechanism": "Mechanistic_Rationale",
            "Safety_Flags": "Safety_Notes",
        }
    )

    if landscape_df is not None and not landscape_df.empty and "Plant" in landscape_df.columns:
        market_cols = [
            c for c in [
                "Plant",
                "EMA_HMPC_Status",
                "WHO_Status",
                "ESCOP_Status",
                "US_Status",
                "UK_Status",
                "Patent_Search_Status",
                "Retail_Products_Status",
            ]
            if c in landscape_df.columns
        ]
        market_small = landscape_df[market_cols].drop_duplicates()
        summary = summary.merge(
            market_small,
            left_on="Candidate_Plant",
            right_on="Plant",
            how="left",
        ).drop(columns=["Plant"], errors="ignore")

    summary = summary.sort_values("Best_R&D_Score", ascending=False).reset_index(drop=True)
    return summary


def _recommendation_label(score, decision_class, safety_notes):
    text = f"{decision_class} {safety_notes}".lower()
    if any(flag in text for flag in ["contraindicat", "hepatotoxic", "toxicity", "major safety"]):
        return "Not recommended until safety is clarified"
    if score >= 80:
        return "Recommended for R&D validation"
    if score >= 60:
        return "Worth validating"
    return "Weak / low priority"


def render_rd_candidates_step(inputs):
    indication = inputs.get("indication", "")
    dosage_form = inputs.get("dosage_form", "")
    market = inputs.get("market", "")

    engine_offline = BotanicalRDCandidateEngine(use_live_search=False)

    # ------------------------------------------------------------------
    # Step 1 — existing knowledge
    # ------------------------------------------------------------------
    st.markdown("### Step 1 — Existing scientific knowledge")
    st.caption(
        "Known plants, active compounds, targets, evidence level, and extraction "
        "information already present in the seed/Supabase knowledge base."
    )

    inventory_df = engine_offline.known_inventory_df(indication)
    st.session_state["rd_inventory_df"] = inventory_df

    if inventory_df.empty:
        st.warning(
            f"No known inventory for '{indication}' yet. Add records to seed_data.py "
            "or Supabase before running candidate discovery."
        )
        return

    st.caption(
        f"{inventory_df['Known_Plant'].nunique()} known plant(s), "
        f"{inventory_df['Known_Compound'].nunique()} known compound(s) already catalogued."
    )
    st.dataframe(inventory_df, use_container_width=True)

    known_plants = _safe_unique(inventory_df["Known_Plant"])

    # ------------------------------------------------------------------
    # Step 2 — market landscape BEFORE candidate discovery
    # ------------------------------------------------------------------
    st.markdown("### Step 2 — Market & competitive landscape")
    st.caption(
        "Check regulatory status, market presence, and patent/retail configuration "
        "for plants already known for this problem. This step comes before candidate "
        "discovery because market saturation affects the R&D decision."
    )

    st.write("**Plants checked in this step:**")
    st.write(", ".join(known_plants))

    if st.button("Step 2: Check market landscape", key="check_market_known"):
        with st.spinner("Checking market and regulatory landscape..."):
            landscape_df = engine_offline.market_landscape_df(known_plants)
        st.session_state["rd_market_landscape_df"] = landscape_df

    landscape_df = st.session_state.get("rd_market_landscape_df")
    if landscape_df is not None:
        st.dataframe(landscape_df, use_container_width=True)
        _market_notice(landscape_df)
    else:
        st.info("Run Step 2 before moving to candidate discovery.")

    # ------------------------------------------------------------------
    # Step 3 — candidate discovery
    # ------------------------------------------------------------------
    st.markdown("### Step 3 — R&D candidate discovery")
    st.caption(
        "Search for alternative or better botanical sources based on shared compounds, "
        "similar compounds, targets, mechanisms, evidence, safety, and novelty."
    )

    col1, col2 = st.columns(2)
    with col1:
        reference_plant = st.text_input(
            "Restrict to reference plant (optional)",
            value="",
            help="Leave empty to analyze every known plant for this indication.",
        )
    with col2:
        reference_compound = st.text_input(
            "Restrict to reference compound (optional)",
            value="",
        )

    use_live_search = st.checkbox(
        "Include live Europe PMC search for candidate scoring",
        value=False,
        help="Keep this off when testing the app to avoid API rate-limit errors such as 429.",
    )

    if st.button("Step 3: Run candidate discovery", type="primary", key="run_candidates"):
        evidence_df = st.session_state.get("evidence_df")
        if not isinstance(evidence_df, pd.DataFrame):
            evidence_df = None

        engine = BotanicalRDCandidateEngine(
            evidence_df=evidence_df,
            use_live_search=use_live_search,
        )

        with st.spinner("Discovering candidate plants..."):
            result_df = engine.run(
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                reference_plant=reference_plant,
                reference_compound=reference_compound,
            )

        st.session_state["rd_candidates_df"] = result_df
        st.session_state["rd_candidates_use_live_search"] = use_live_search

    result_df = st.session_state.get("rd_candidates_df")
    if result_df is None:
        st.info("Run Step 3 after reviewing Step 1 and Step 2.")
        return

    if result_df.empty:
        st.warning("No candidate rows were generated for this indication.")
        return

    st.success(f"{len(result_df)} candidate rows generated.")

    with st.expander("Raw candidate rows", expanded=False):
        st.dataframe(result_df, use_container_width=True)
        st.download_button(
            "Download raw candidate table (CSV)",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name="botanical_rd_candidates_raw.csv",
            mime="text/csv",
        )

    # ------------------------------------------------------------------
    # Step 4 — decision engine
    # ------------------------------------------------------------------
    st.markdown("### Step 4 — Decision engine")
    st.caption(
        "Candidate-level decision table. Duplicate compound rows are collapsed so "
        "the user sees one decision line per candidate plant."
    )

    decision_df = _build_decision_summary(result_df, landscape_df)
    if decision_df.empty:
        st.warning("Decision table could not be generated.")
        return

    decision_df["Final_Recommendation_Class"] = decision_df.apply(
        lambda row: _recommendation_label(
            float(row.get("Best_R&D_Score", 0) or 0),
            row.get("Decision_Class", ""),
            row.get("Safety_Notes", ""),
        ),
        axis=1,
    )

    st.dataframe(decision_df, use_container_width=True)
    st.download_button(
        "Download decision table (CSV)",
        data=decision_df.to_csv(index=False).encode("utf-8"),
        file_name="botanical_rd_decision_table.csv",
        mime="text/csv",
    )

    # ------------------------------------------------------------------
    # Step 5 — final recommendation
    # ------------------------------------------------------------------
    st.markdown("### Step 5 — Final recommendation")
    top = decision_df.iloc[0]

    st.success(
        f"Top candidate: {top['Candidate_Plant']} — "
        f"{top['Final_Recommendation_Class']} "
        f"(score: {top['Best_R&D_Score']})."
    )

    st.write("**Why this candidate appears first:**")
    st.write(top.get("Rationale", "No rationale available."))

    st.write("**Recommended next validation work:**")
    st.write(
        "Confirm literature evidence, verify regulatory status for the exact market, "
        "check supplier availability and extract standardization, then validate the "
        "candidate experimentally before any product claim."
    )
