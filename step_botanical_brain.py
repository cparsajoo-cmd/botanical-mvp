import streamlit as st
import pandas as pd

from botanical_brain_engine import UniversalBotanicalBrainEngine


def render_botanical_brain_step(inputs=None):
    st.markdown("---")
    st.header("Universal Botanical Brain")
    st.caption("Target / compound → active compounds → candidate plants → score")

    st.write(
        "This is the core discovery engine. It can start from any biological target, "
        "biomolecule, or active compound. It searches compound-target links, then maps "
        "active compounds to candidate plants."
    )

    mode = st.radio(
        "Start discovery from:",
        ["Biological target / biomolecule", "Active compound"],
        horizontal=True,
        key="brain_mode",
    )

    if mode == "Biological target / biomolecule":
        query = st.text_input(
            "Enter target / biomolecule",
            value="Myeloperoxidase",
            key="brain_target_query",
        )
        engine_mode = "target"
    else:
        query = st.text_input(
            "Enter active compound",
            value="Rosmarinic acid",
            key="brain_compound_query",
        )
        engine_mode = "compound"

    if st.button("Run Universal Botanical Brain", key="run_universal_brain"):
        with st.spinner("Running universal botanical discovery..."):
            evidence_df = st.session_state.get("evidence_df")

            if evidence_df is None:
                evidence_df = st.session_state.get("knowledge_df")

            if evidence_df is None:
                evidence_df = pd.DataFrame()

            engine = UniversalBotanicalBrainEngine(evidence_df=evidence_df)

            result = engine.discover(
                query=query,
                mode=engine_mode,
            )

            st.session_state["botanical_brain_df"] = result

    df = st.session_state.get("botanical_brain_df")

    if df is None:
        return

    if df.empty:
        st.warning(
            "No candidates found. Try a broader target name, for example: "
            "MPO, myeloperoxidase, acetylcholinesterase, GABA, NF-kB, COX."
        )
        return

    st.success(f"{len(df)} botanical discovery candidates found.")

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download Universal Botanical Brain results as CSV",
        data=csv,
        file_name="universal_botanical_brain_results.csv",
        mime="text/csv",
    )
