import streamlit as st
import pandas as pd

from disease_target_engine import DiseaseTargetEngine


def render_target_step(inputs):
    st.markdown("---")
    st.header("Step 10 — Disease → Target Discovery")

    knowledge = st.session_state.get("knowledge_df")

    if knowledge is None or knowledge.empty:
        st.info("First run Step 9 — Scientific Knowledge Extraction.")
        return

    if st.button("Step 10: Discover biological targets"):
        engine = DiseaseTargetEngine()

        result = engine.discover(
            inputs.get("indication", ""),
            knowledge,
        )

        df = pd.DataFrame([x.__dict__ for x in result])

        st.session_state["target_df"] = df

    df = st.session_state.get("target_df")

    if df is None:
        return

    if df.empty:
        st.warning("No biological targets found yet.")
        return

    st.success(f"{len(df)} targets found")
    st.dataframe(df, use_container_width=True, hide_index=True)
