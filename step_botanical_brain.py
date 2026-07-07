import streamlit as st
import pandas as pd

from botanical_brain_engine import BotanicalBrainEngine


def render_botanical_brain_step(inputs=None):
    st.markdown("---")
    st.header("Step 15 — Botanical Brain Discovery")

    st.write(
        "This engine starts from an active compound or biological target, "
        "finds shared mechanisms, identifies related active compounds, "
        "then proposes plants containing those compounds."
    )

    mode = st.radio(
        "Start discovery from:",
        ["Active compound", "Biological target"],
        horizontal=True,
    )

    if mode == "Active compound":
        query = st.text_input(
            "Enter active compound",
            value="Rosmarinic acid",
            key="brain_compound_input",
        )
    else:
        query = st.text_input(
            "Enter biological target / biomolecule",
            value="Acetylcholinesterase",
            key="brain_target_input",
        )

    if st.button("Run Botanical Brain Discovery"):
        engine = BotanicalBrainEngine()

        if mode == "Active compound":
            result = engine.discover_from_compound(query)
        else:
            result = engine.discover_from_target(query)

        st.session_state["botanical_brain_df"] = result

    df = st.session_state.get("botanical_brain_df")

    if df is None:
        return

    if df.empty:
        st.warning("No botanical brain candidates found yet.")
        return

    st.success(f"{len(df)} mechanism-based botanical candidates found.")

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download Botanical Brain results as CSV",
        data=csv,
        file_name="botanical_brain_discovery.csv",
        mime="text/csv",
    )
