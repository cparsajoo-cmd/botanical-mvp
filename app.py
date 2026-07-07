import streamlit as st

from evidence_database import load_evidence_database
from step_inputs import render_inputs
from step_rd_candidates import render_rd_candidate_step


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)


st.title("🌿 Botanical Product Intelligence Platform")

st.caption(
    "Central botanical R&D candidate intelligence engine"
)


inputs = render_inputs()


try:
    st.session_state["evidence_df"] = load_evidence_database()
except Exception:
    st.session_state["evidence_df"] = None


st.markdown("---")

st.info(
    "Workflow: define product/problem → identify known reference plants and "
    "compounds → find same/similar compounds in alternative plants → evaluate "
    "extraction, co-compounds, safety, interactions, market, novelty → decide."
)


render_rd_candidate_step(inputs)
