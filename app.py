import streamlit as st

from step_inputs import render_inputs
from step_question import render_question_step
from step_evidence import render_evidence_step
from step_rd_candidates import render_rd_candidates_step
from step_import_data import render_import_step
from evidence_database import load_evidence_database_with_meta

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Scientific evidence, safety, regulation and candidate prioritization for botanical R&D")

inputs = render_inputs()



@st.cache_data(ttl=3600, show_spinner="Loading evidence database...")
def _cached_evidence_with_meta():
    # Cached across reruns and sessions for one hour. The previous 5-minute TTL
    # caused the full evidence table to cross the Supabase network boundary
    # repeatedly during normal interactive use, materially increasing Egress.
    # A one-hour TTL keeps the app responsive and cuts repeated full-table
    # transfers without changing any scientific/scoring behavior. It is still
    # bounded (not permanent), and — critically — does NOT
    # swallowing errors: any failure comes back as an explicit
    # data_source_mode instead of a silently empty/None result.
    return load_evidence_database_with_meta()


evidence_df, evidence_meta = _cached_evidence_with_meta()
st.session_state["evidence_df"] = evidence_df
st.session_state["evidence_meta"] = evidence_meta

render_question_step(inputs)
render_evidence_step(inputs)
render_rd_candidates_step(inputs)

with st.expander("Data import", expanded=False):
    render_import_step()

st.markdown("---")

with st.expander("Evidence database", expanded=False):
    mode = evidence_meta["data_source_mode"]

    if mode == "Full Supabase data":
        st.success(
            f"Evidence database ready — {evidence_meta['returned_records']} of "
            f"{evidence_meta['total_records']} total records loaded."
        )
    elif mode == "Partial Supabase data":
        total = evidence_meta["total_records"]
        total_text = str(total) if total is not None else "unknown"
        st.warning(
            f"Evidence database partially available — {evidence_meta['returned_records']} of "
            f"{total_text} total records were retrieved. Analysis below is running "
            f"on an incomplete dataset; do not treat results as full coverage."
        )
    else:  # "Unavailable"
        st.error(
            "Could not load the evidence database "
            f"({evidence_meta.get('error') or 'unknown error'}). "
            "Live evidence data is unavailable for this session."
        )

    if not evidence_df.empty:
        preview_rows = st.slider(
            "Rows to preview", min_value=10, max_value=200, value=50, step=10,
            help="Full table isn't rendered by default — pick how many rows to preview.",
        )
        st.dataframe(evidence_df.head(preview_rows), width="stretch")
    else:
        st.caption("No rows to preview.")
