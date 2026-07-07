import streamlit as st

from step_inputs import render_inputs
from step_question import render_question_step
from step_evidence import render_evidence_step
from step_rd_candidates import render_rd_candidates_step
from evidence_database import load_evidence_database

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("AI Botanical R&D Decision Intelligence Platform")

inputs = render_inputs()

try:
    evidence_df = load_evidence_database()
    st.session_state["evidence_df"] = evidence_df
except Exception:
    evidence_df = None

st.markdown("## Core workflow")
st.info(
    "Define project → understand the question → (optionally) collect fresh "
    "online evidence → discover R&D candidates (known inventory, "
    "alternative plants, scoring, decision table)."
)

render_question_step(inputs)
render_evidence_step(inputs)
render_rd_candidates_step(inputs)

st.markdown("---")

with st.expander("Supabase evidence database preview"):
    if evidence_df is not None:
        st.write(f"Total evidence records: {len(evidence_df)}")
        st.dataframe(evidence_df, use_container_width=True)
    else:
        st.warning("Could not load Supabase evidence database preview.")
