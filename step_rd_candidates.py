import pandas as pd
import streamlit as st

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def _unique_nonempty(values):
    seen = set()
    out = []
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() == "nan":
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _recommendation_block(result_df):
    if result_df is None or result_df.empty:
        st.info("Run Step 3 first to generate final recommendations.")
        return

    df = result_df.copy()
    if "R&D_Opportunity_Score" in df.columns:
        df["R&D_Opportunity_Score"] = pd.to_numeric(
            df["R&D_Opportunity_Score"], errors="coerce"
        ).fillna(0)
        df = df.sort_values("R&D_Opportunity_Score", ascending=False)

    plant_col = "Alternative_Plant" if "Alternative_Plant" in df.columns else df.columns[0]
    decision_col = "Decision_Class" if "Decision_Class" in df.columns else None

    # One visible recommendation per plant, using the best scoring row.
    best_rows = df.drop_duplicates(subset=[plant_col], keep="first")

    recommended = best_rows
    if decision_col:
        recommended = best_rows[
            best_rows[decision_col].astype(str).str.contains(
                "strong|promising|recommend", case=False, na=False
            )
        ]
        if recommended.empty:
            recommended = best_rows.head(5)

    st.markdown("#### Recommended / worth validating")
    display_cols = [
        col for col in [
            "Alternative_Plant",
            "Shared_or_Similar_Compound",
            "Target_or_Mechanism",
            "R&D_Opportunity_Score",
            "Decision_Class",
            "Safety_Flags",
            "Market_Status",
            "Novelty_Status",
            "Rationale",
        ] if col in recommended.columns
    ]
    st.dataframe(recommended[display_cols].head(10), use_container_width=True)

    if decision_col:
        weak = best_rows[
            best_rows[decision_col].astype(str).str.contains(
                "weak|reject|not", case=False, na=False
            )
        ]
        if not weak.empty:
            st.markdown("#### Weak / not recommended")
            st.dataframe(weak[display_cols].head(10), use_container_width=True)


def render_rd_candidates_step(inputs):
    indication = inputs.get("indication", "")
    dosage_form = inputs.get("dosage_form", "")
    market = inputs.get("market", "")

    evidence_df = st.session_state.get("evidence_df")
    if not isinstance(evidence_df, pd.DataFrame):
        evidence_df = None

    offline_engine = BotanicalRDCandidateEngine(
        evidence_df=evidence_df,
        use_live_search=False,
    )

    inventory_df = offline_engine.known_inventory_df(indication)
    known_plants = _unique_nonempty(inventory_df.get("Known_Plant", [])) if not inventory_df.empty else []

    # ------------------------------------------------------------------
    # Step 1 — Market first, before scientific deep dive and before R&D
    # candidate generation.
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("## Step 1 — Market & competitive landscape")
    st.caption(
        "What already exists for this R&D question: known commercial botanical "
        "sources, regulatory status, patent-search readiness, and retail/brand "
        "search readiness. This step comes before candidate discovery."
    )

    if not known_plants:
        st.warning(
            f"No known plant inventory found yet for '{indication}'. Add seed data "
            "before running a meaningful market landscape."
        )
    else:
        st.write("**Known plants used for the first market check:**")
        st.write(", ".join(known_plants))

        live_market = st.checkbox(
            "Include live patent / retail search if API keys are configured",
            value=False,
            help="Keep this off unless EPO/retail search keys are configured. It avoids rate-limit errors.",
            key="rd_market_live_checkbox",
        )

        if st.button("Step 1: Check market & competitive landscape", type="primary"):
            market_engine = BotanicalRDCandidateEngine(
                evidence_df=evidence_df,
                use_live_search=live_market,
            )
            with st.spinner("Checking market and regulatory landscape..."):
                landscape_df = market_engine.market_landscape_df(known_plants)
            st.session_state["rd_market_landscape_df"] = landscape_df

        landscape_df = st.session_state.get("rd_market_landscape_df")
        if isinstance(landscape_df, pd.DataFrame) and not landscape_df.empty:
            st.dataframe(landscape_df, use_container_width=True)

            if "Patent_Search_Status" in landscape_df.columns and (
                landscape_df["Patent_Search_Status"] == "Not configured"
            ).all():
                st.info(
                    "Patent search is not configured. This is expected unless "
                    "EPO_OPS_KEY and EPO_OPS_SECRET are set."
                )
            if "Retail_Products_Status" in landscape_df.columns and (
                landscape_df["Retail_Products_Status"] == "Not configured"
            ).all():
                st.info(
                    "Retail/brand scanning is not configured. Set a paid web-search "
                    "API key only when you choose a provider."
                )

    # ------------------------------------------------------------------
    # Step 2 — Scientific knowledge after market overview.
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("## Step 2 — Existing scientific knowledge")
    st.caption(
        "Known plants, active compounds, targets/mechanisms, evidence level, "
        "and typical extraction already catalogued for this problem."
    )

    if inventory_df.empty:
        st.warning(
            f"No known plants/compounds/targets for '{indication}' yet in the "
            "seed knowledge base. Extend seed_data.py to add coverage."
        )
    else:
        st.caption(
            f"{inventory_df['Known_Plant'].nunique()} known plant(s), "
            f"{inventory_df['Known_Compound'].nunique()} known compound(s) catalogued."
        )
        st.dataframe(inventory_df, use_container_width=True)

    # ------------------------------------------------------------------
    # Step 3 — Candidate discovery + decision engine.
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("## Step 3 — R&D candidate discovery & decision engine")
    st.caption(
        "Now the engine searches for alternative or better botanical candidates "
        "and scores them using evidence, mechanism plausibility, novelty, safety, "
        "regulatory feasibility, and market opportunity."
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
        "Include live Europe PMC evidence search (slower; may hit rate limits)",
        value=False,
        key="rd_live_evidence_checkbox",
    )

    if st.button("Step 3: Run R&D candidate discovery", type="primary"):
        engine = BotanicalRDCandidateEngine(
            evidence_df=evidence_df,
            use_live_search=use_live_search,
        )
        with st.spinner("Discovering and scoring R&D candidates..."):
            result_df = engine.run(
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                reference_plant=reference_plant,
                reference_compound=reference_compound,
            )
        st.session_state["rd_candidates_df"] = result_df

    result_df = st.session_state.get("rd_candidates_df")

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        st.success(f"{len(result_df)} candidate rows generated.")
        st.dataframe(result_df, use_container_width=True)
        st.download_button(
            "Download decision table (CSV)",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name="botanical_rd_candidates.csv",
            mime="text/csv",
        )
    elif isinstance(result_df, pd.DataFrame) and result_df.empty:
        st.warning(
            "No R&D candidates found for this indication. Extend seed_data.py or Supabase records."
        )

    # ------------------------------------------------------------------
    # Step 4 — Final recommendation.
    # ------------------------------------------------------------------
    st.markdown("---")
    st.markdown("## Step 4 — Final recommendation")
    st.caption(
        "A concise R&D recommendation based on the decision table generated in Step 3."
    )
    _recommendation_block(result_df)
