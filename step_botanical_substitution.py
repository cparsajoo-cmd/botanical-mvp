import streamlit as st
import pandas as pd

from botanical_substitution_engine import BotanicalSubstitutionEngine


def render_botanical_substitution_step(inputs):
    st.markdown("---")
    st.header("Botanical Substitution & R&D Candidate Discovery")

    st.write(
        "Find alternative plants containing the same active compound, then compare "
        "concentration, extraction method, co-compounds, safety, interactions, and R&D potential."
    )

    c1, c2 = st.columns(2)

    with c1:
        compound = st.text_input(
            "Active compound",
            value="Rosmarinic acid",
            key="substitution_compound",
        )

    with c2:
        reference_plant = st.text_input(
            "Reference plant",
            value="Melissa officinalis",
            key="substitution_reference_plant",
        )

    if st.button("Run Botanical Substitution Discovery"):
        evidence_df = st.session_state.get("evidence_df")

        if evidence_df is None:
            evidence_df = st.session_state.get("knowledge_df")

        if evidence_df is None:
            evidence_df = pd.DataFrame()

        engine = BotanicalSubstitutionEngine(evidence_df=evidence_df)

        df = engine.discover(
            compound=compound,
            reference_plant=reference_plant,
            indication=inputs.get("indication", ""),
            dosage_form=inputs.get("dosage_form", ""),
            market=inputs.get("target_market", ""),
        )

        st.session_state["botanical_substitution_df"] = df

    df = st.session_state.get("botanical_substitution_df")

    if df is None:
        return

    if df.empty:
        st.warning("No alternative botanical sources found yet.")
        return

    st.success(f"{len(df)} alternative botanical candidates found.")

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download substitution discovery results",
        data=csv,
        file_name="botanical_substitution_discovery.csv",
        mime="text/csv",
    )
