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


def _get_evidence_df():
    evidence_df = st.session_state.get("evidence_df")
    if isinstance(evidence_df, pd.DataFrame):
        return evidence_df
    return None


def _offline_engine():
    return BotanicalRDCandidateEngine(
        evidence_df=_get_evidence_df(),
        use_live_search=False,
    )


def _recommendation_block(result_df):
    if result_df is None or not isinstance(result_df, pd.DataFrame) or result_df.empty:
        st.warning("Run Step 5 first, then generate the final recommendation.")
        return

    df = result_df.copy()

    if "R&D_Opportunity_Score" in df.columns:
        df["R&D_Opportunity_Score"] = pd.to_numeric(
            df["R&D_Opportunity_Score"], errors="coerce"
        ).fillna(0)
        df = df.sort_values("R&D_Opportunity_Score", ascending=False)

    plant_col = "Alternative_Plant" if "Alternative_Plant" in df.columns else df.columns[0]
    decision_col = "Decision_Class" if "Decision_Class" in df.columns else None

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

    st.markdown("### ✅ Recommended / worth validating")
    st.dataframe(recommended[display_cols].head(10), use_container_width=True)

    if decision_col:
        weak = best_rows[
            best_rows[decision_col].astype(str).str.contains(
                "weak|reject|not", case=False, na=False
            )
        ]
        if not weak.empty:
            st.markdown("### 🔴 Weak / not recommended")
            st.dataframe(weak[display_cols].head(10), use_container_width=True)


def render_rd_candidates_step(inputs):
    indication = inputs.get("indication", "")
    dosage_form = inputs.get("dosage_form", "")
    market = inputs.get("market", "")

    st.markdown("---")
    st.markdown("## Step 3 — Market & Competitive Landscape")

    st.caption(
        "Check what already exists in the market: existing botanical products, "
        "known plants, regulatory status, patent readiness, retail/brand search readiness, "
        "and market saturation signals."
    )

    live_market = st.checkbox(
        "Include live patent / retail search if API keys are configured",
        value=False,
        help="Keep this off unless external API keys are configured.",
        key="rd_market_live_checkbox",
    )

    if st.button("Run Market Analysis", type="primary", key="run_step1_market"):
        try:
            offline_engine = _offline_engine()
            inventory_df = offline_engine.known_inventory_df(indication)

            known_plants = (
                _unique_nonempty(inventory_df.get("Known_Plant", []))
                if not inventory_df.empty
                else []
            )

            st.session_state["rd_inventory_df_internal"] = inventory_df
            st.session_state["rd_known_plants"] = known_plants

            if not known_plants:
                st.session_state["rd_market_landscape_df"] = pd.DataFrame()
                st.warning(
                    f"No known plant inventory found for '{indication}'. "
                    "Add seed data before running market analysis."
                )
            else:
                market_engine = BotanicalRDCandidateEngine(
                    evidence_df=_get_evidence_df(),
                    use_live_search=live_market,
                )

                with st.spinner("Checking market and competitive landscape..."):
                    landscape_df = market_engine.market_landscape_df(known_plants)

                st.session_state["rd_market_landscape_df"] = landscape_df
                st.success("✅ Market analysis completed.")

        except Exception as e:
            st.error(f"Market analysis failed: {e}")

    known_plants = st.session_state.get("rd_known_plants", [])
    landscape_df = st.session_state.get("rd_market_landscape_df")

    if known_plants:
        st.write("**Known plants used for market check:**")
        st.write(", ".join(known_plants))

    if isinstance(landscape_df, pd.DataFrame) and not landscape_df.empty:
        st.dataframe(landscape_df, use_container_width=True)

    st.markdown("---")
    st.markdown("## Step 4 — Existing Scientific Knowledge")

    st.caption(
        "Show current scientific knowledge: known plants, compounds, targets, mechanisms, "
        "evidence level, extraction information, safety notes, and regulatory notes."
    )

    if st.button("Run Scientific Knowledge Analysis", type="primary", key="run_step2_science"):
        try:
            offline_engine = _offline_engine()
            inventory_df = offline_engine.known_inventory_df(indication)
            st.session_state["rd_inventory_df"] = inventory_df

            if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty:
                st.success("✅ Scientific knowledge analysis completed.")
            else:
                st.warning(
                    f"No scientific inventory found for '{indication}' in the seed database."
                )

        except Exception as e:
            st.error(f"Scientific knowledge analysis failed: {e}")

    inventory_df = st.session_state.get("rd_inventory_df")

    if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty:
        if "Known_Plant" in inventory_df.columns and "Known_Compound" in inventory_df.columns:
            st.caption(
                f"{inventory_df['Known_Plant'].nunique()} known plant(s), "
                f"{inventory_df['Known_Compound'].nunique()} known compound(s) catalogued."
            )
        st.dataframe(inventory_df, use_container_width=True)

    st.markdown("---")
    st.markdown("## Step 5 — R&D Candidate Discovery & Decision Engine")

    st.caption(
        "Generate alternative botanical candidates and score them using evidence, "
        "mechanism plausibility, novelty, safety, regulatory feasibility, and market opportunity."
    )

    col1, col2 = st.columns(2)

    with col1:
        reference_plant = st.text_input(
            "Restrict to reference plant (optional)",
            value="",
            help="Leave empty to analyze every known plant for this indication.",
            key="rd_reference_plant",
        )

    with col2:
        reference_compound = st.text_input(
            "Restrict to reference compound (optional)",
            value="",
            key="rd_reference_compound",
        )

    use_live_search = st.checkbox(
        "Include live Europe PMC evidence search",
        value=False,
        help="Keep this off unless needed. It may hit rate limits.",
        key="rd_live_evidence_checkbox",
    )

    if st.button("Run Candidate Discovery", type="primary", key="run_step3_candidates"):
        try:
            engine = BotanicalRDCandidateEngine(
                evidence_df=_get_evidence_df(),
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

            if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                st.success(f"✅ {len(result_df)} candidate rows generated.")
            else:
                st.warning("No R&D candidates found.")

        except Exception as e:
            st.error(f"Candidate discovery failed: {e}")

    result_df = st.session_state.get("rd_candidates_df")

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        st.dataframe(result_df, use_container_width=True)

        st.download_button(
            "Download decision table (CSV)",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name="botanical_rd_candidates.csv",
            mime="text/csv",
        )

    st.markdown("---")
    st.markdown("## Step 6 — Final Recommendation")

    st.caption(
        "Generate a concise R&D recommendation based on the decision table produced in Step 5."
    )

    if st.button("Generate Final Recommendation", type="primary", key="run_step4_recommendation"):
        st.session_state["show_final_recommendation"] = True

    if st.session_state.get("show_final_recommendation"):
        _recommendation_block(result_df)
