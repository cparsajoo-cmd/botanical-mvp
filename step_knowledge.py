import streamlit as st
import pandas as pd

from knowledge_extraction_engine import ScientificKnowledgeExtractionEngine


def render_knowledge_step(inputs):
    st.markdown("---")
    st.markdown("## Step 8.7 — Scientific Knowledge Extraction")

    if st.button("Step 8.7: Extract target / mechanism knowledge"):
        with st.spinner("Extracting target, mechanism, and indication knowledge..."):
            engine = ScientificKnowledgeExtractionEngine()
            knowledge_df = engine.extract(inputs=inputs)

        st.session_state["knowledge_df"] = knowledge_df

    knowledge_df = st.session_state.get("knowledge_df")

    if knowledge_df is None:
        return

    if knowledge_df.empty:
        st.warning("No structured target/mechanism knowledge extracted yet.")
        return

    st.success(f"{len(knowledge_df)} structured knowledge records extracted.")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Unique plants", knowledge_df["Plant"].nunique())

    with c2:
        st.metric("Targets found", knowledge_df["Target"].replace("", pd.NA).dropna().nunique())

    with c3:
        st.metric("Mechanisms found", knowledge_df["Mechanism"].replace("", pd.NA).dropna().nunique())

    st.markdown("### Extracted scientific knowledge")
    st.dataframe(knowledge_df, use_container_width=True, hide_index=True)

    csv = knowledge_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download extracted scientific knowledge as CSV",
        data=csv,
        file_name="scientific_knowledge_extraction.csv",
        mime="text/csv",
    )
