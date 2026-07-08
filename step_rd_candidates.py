import streamlit as st
import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def render_rd_candidates_step(inputs):
    st.markdown("## R&D Candidate Discovery")
    st.caption(
        "Starts from your product/problem, lists what is already known "
        "(plants, compounds, targets, evidence, market), then searches for "
        "better or alternative botanical sources of the same active "
        "compounds."
    )

    indication = inputs.get("indication", "")
    dosage_form = inputs.get("dosage_form", "")
    market = inputs.get("market", "")

    # --- Step 1: known inventory, shown immediately (offline, instant) ---
    st.markdown("### Step 1 — Known inventory for this problem")
    inventory_engine = BotanicalRDCandidateEngine(use_live_search=False)
    inventory_df = inventory_engine.known_inventory_df(indication)

    if inventory_df.empty:
        st.warning(
            f"No known plants/compounds/targets for '{indication}' yet in "
            "the seed knowledge base. Extend seed_data.py "
            "(PLANT_COMPOUNDS / COMPOUND_TARGETS / TARGET_DISEASES) to add it."
        )
    else:
        st.caption(
            f"{inventory_df['Known_Plant'].nunique()} known plant(s), "
            f"{inventory_df['Known_Compound'].nunique()} known compound(s) already catalogued for this problem."
        )
        st.dataframe(inventory_df, use_container_width=True)

    st.markdown("### Step 2 — Alternative/better botanical sources")

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
        "Include live Europe PMC search (slower, needs internet)", value=True
    )

    if not st.button("Run R&D candidate discovery", type="primary"):
        return

    evidence_df = st.session_state.get("evidence_df")
    if not isinstance(evidence_df, pd.DataFrame):
        evidence_df = None

    engine = BotanicalRDCandidateEngine(
        evidence_df=evidence_df,
        use_live_search=use_live_search,
    )

    with st.spinner("Discovering R&D candidates..."):
        result_df = engine.run(
            indication=indication,
            dosage_form=dosage_form,
            market=market,
            reference_plant=reference_plant,
            reference_compound=reference_compound,
        )

    if result_df.empty:
        st.warning(
            "No known plants/compounds found for this indication in the "
            "seed knowledge base yet. Add entries to seed_data.py "
            "(PLANT_COMPOUNDS / COMPOUND_TARGETS / TARGET_DISEASES) to "
            "extend coverage."
        )
        return

    st.session_state["rd_candidates_df"] = result_df

    st.success(f"{len(result_df)} candidate rows generated.")
    st.dataframe(result_df, use_container_width=True)

    st.download_button(
        "Download decision table (CSV)",
        data=result_df.to_csv(index=False).encode("utf-8"),
        file_name="botanical_rd_candidates.csv",
        mime="text/csv",
    )

    # --- Step 3: market landscape (regulatory status, patents, retail) ---
    st.markdown("### Step 3 — Market landscape")
    st.caption(
        "What already exists in the market for these plants: EU regulatory "
        "status (free, curated), patents (free API — needs a key), and "
        "retail/brand products (paid search API — needs a key)."
    )

    plants_in_results = result_df["Alternative_Plant"].dropna().unique().tolist()
    if st.button("Check market landscape for these plants"):
        with st.spinner("Checking regulatory status, patents, and retail presence..."):
            landscape_df = engine.market_landscape_df(plants_in_results)
        st.dataframe(landscape_df, use_container_width=True)
        if (landscape_df["Patent_Search_Status"] == "Not configured").all():
            st.info(
                "Patent search isn't configured yet. Set EPO_OPS_KEY / "
                "EPO_OPS_SECRET (free registration at developers.epo.org) "
                "to enable it."
            )
        if (landscape_df["Retail_Products_Status"] == "Not configured").all():
            st.info(
                "Retail/brand product scanning needs a paid search API "
                "(e.g. Bing Web Search, SerpAPI). Set SEARCH_API_KEY once "
                "you've picked a provider."
            )
