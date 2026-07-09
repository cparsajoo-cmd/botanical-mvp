import streamlit as st

from step_inputs import render_inputs
from step_rd_candidates import render_rd_candidates_step
from step_evidence import render_evidence_step
from step_import_data import render_import_step
from evidence_database import load_evidence_database

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("AI Botanical R&D Decision Intelligence Platform")

# Step 0 is rendered here.
inputs = render_inputs()

try:
    evidence_df = load_evidence_database()
    st.session_state["evidence_df"] = evidence_df
except Exception:
    evidence_df = None

st.markdown("---")
st.markdown("## Ordered R&D workflow")
st.info(
    "Step 0: define the problem → Step 1: existing scientific knowledge → "
    "Step 2: market and competitive landscape → Step 3: candidate discovery → "
    "Step 4: decision scoring → Step 5: final recommendation."
)

render_rd_candidates_step(inputs)

st.markdown("---")
with st.expander("Optional tools — online evidence ingestion and database preview", expanded=False):
    st.caption(
        "These tools are useful for enriching the database, but they are not part "
        "of the main R&D decision sequence above."
    )
    render_evidence_step(inputs)
    render_import_step()

    st.markdown("### Supabase evidence database preview")
    if evidence_df is not None:
        st.write(f"Total evidence records: {len(evidence_df)}")
        st.dataframe(evidence_df, use_container_width=True)
    else:
        st.warning("Could not load Supabase evidence database preview.")
