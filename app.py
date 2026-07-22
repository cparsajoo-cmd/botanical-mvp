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
st.caption("AI Botanical R&D Decision Intelligence Platform")

inputs = render_inputs()


with st.expander("ℹ️ Core workflow (Step 0 → Step 6)", expanded=False):
    st.caption(
        "Step 0: define the R&D question → Step 1: understand the question → "
        "Step 2: collect online evidence → Step 3: market & competitive landscape → "
        "Step 4: existing scientific knowledge → Step 5: R&D candidate discovery "
        "and decision engine → Step 6: final recommendation."
    )


@st.cache_data(ttl=300, show_spinner="Loading Supabase evidence database...")
def _cached_evidence_with_meta():
    # Cached (not re-fetched on every rerun/widget interaction, which is
    # what happened before) but with a short TTL, and — critically — NOT
    # swallowing errors: any failure comes back as an explicit
    # data_source_mode instead of a silently empty/None result.
    return load_evidence_database_with_meta()


evidence_df, evidence_meta = _cached_evidence_with_meta()
st.session_state["evidence_df"] = evidence_df
st.session_state["evidence_meta"] = evidence_meta

render_question_step(inputs)
render_evidence_step(inputs)
render_rd_candidates_step(inputs)

with st.expander("Optional: import / ingest data"):
    render_import_step()

st.markdown("---")

with st.expander("Supabase evidence database preview", expanded=False):
    mode = evidence_meta["data_source_mode"]

    if mode == "Full Supabase data":
        st.success(
            f"Full Supabase data — {evidence_meta['returned_records']} of "
            f"{evidence_meta['total_records']} total records loaded."
        )
    elif mode == "Partial Supabase data":
        total = evidence_meta["total_records"]
        total_text = str(total) if total is not None else "unknown"
        st.warning(
            f"Partial Supabase data — only {evidence_meta['returned_records']} of "
            f"{total_text} total records were retrieved. Analysis below is running "
            f"on an incomplete dataset; do not treat results as full coverage."
        )
    else:  # "Unavailable"
        st.error(
            "Could not load the Supabase evidence database preview "
            f"({evidence_meta.get('error') or 'unknown error'}). "
            "No evidence data is available for this session — Step 2-5 results "
            "will be based on whatever local/seed data those steps fall back to, "
            "not live Supabase evidence."
        )

    if not evidence_df.empty:
        preview_rows = st.slider(
            "Rows to preview", min_value=10, max_value=200, value=50, step=10,
            help="Full table isn't rendered by default — pick how many rows to preview.",
        )
        st.dataframe(evidence_df.head(preview_rows), width="stretch")
    else:
        st.caption("No rows to preview.")
