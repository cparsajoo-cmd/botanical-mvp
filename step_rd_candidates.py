import streamlit as st
import pandas as pd

from botanical_rd_engine import BotanicalRDCandidateEngine


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
