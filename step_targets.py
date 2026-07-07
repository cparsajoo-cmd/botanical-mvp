import streamlit as st
import pandas as pd

from disease_target_engine import DiseaseTargetEngine


def render_target_step(inputs):

    st.markdown("---")
    st.header("Step 8.95 — Disease → Target Discovery")

    if st.button("Discover biological targets"):

        engine=DiseaseTargetEngine()

        knowledge=st.session_state["knowledge_df"]

        result=engine.discover(
            inputs["indication"],
            knowledge
        )

        df=pd.DataFrame([x.__dict__ for x in result])

        st.session_state["target_df"]=df

    if "target_df" in st.session_state:

        df=st.session_state["target_df"]

        st.success(f"{len(df)} targets found")

        st.dataframe(df,use_container_width=True)
