import streamlit as st
import pandas as pd

from knowledge_extraction_engine import KnowledgeExtractionEngine


def render_knowledge_step(inputs):
    st.markdown("---")
    st.markdown("## Step 8.7 — Knowledge Extraction Engine")

    st.write(
        "This extracts structured plant–compound–target–mechanism knowledge from the evidence database."
    )

    if st.button("Step 8.7: Extract structured knowledge"):
        with st.spinner("Extracting structured scientific knowledge..."):
            engine = KnowledgeExtractionEngine()
            knowledge_df = engine.extract(inputs=inputs)

        st.session_state["knowledge_df"] = knowledge_df

    knowledge_df = st.session_state.get("knowledge_df")

    if knowledge_df is None:
        return

    if knowledge_df.empty:
        st.warning("No structured knowledge extracted yet.")
        return

    st.success(f"{len(knowledge_df)} structured knowledge records extracted.")

    st.dataframe(
        knowledge_df,
        use_container_width=True,
        hide_index=True,
    )

    csv = knowledge_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download extracted knowledge as CSV",
        data=csv,
        file_name="extracted_knowledge.csv",
        mime="text/csv",
    )
