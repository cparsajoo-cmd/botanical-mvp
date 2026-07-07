import inspect
import streamlit as st

from step_inputs import render_inputs
from step_question import render_question_step
from step_seed import render_seed_step
from step_discovery import render_discovery_step
from step_evidence import render_evidence_step
from step_ranking import render_ranking_step
from step_opportunity import render_opportunity_step
from step_market import render_market_step
from step_botanical_substitution import render_botanical_substitution_step
from step_whitespace import render_whitespace_step
from step_knowledge import render_knowledge_step
from step_targets import render_target_step
from step_mechanism import render_mechanism_step
from step_target_discovery import render_target_discovery_step
from step_graph import render_graph_step
from step_download import render_download_step
from evidence_database import load_evidence_database


def run_step(func, inputs=None):
    try:
        sig = inspect.signature(func)
        if len(sig.parameters) == 0:
            return func()
        return func(inputs)
    except TypeError:
        return func()


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
    "Define project → discover candidates → collect evidence → rank → "
    "find alternative botanical sources for active compounds → assess R&D opportunity → export."
)

run_step(render_question_step, inputs)
run_step(render_seed_step, inputs)
run_step(render_discovery_step, inputs)
run_step(render_evidence_step, inputs)
run_step(render_ranking_step, inputs)
run_step(render_opportunity_step, inputs)
run_step(render_market_step, inputs)

render_botanical_substitution_step(inputs)

run_step(render_whitespace_step, inputs)
run_step(render_knowledge_step, inputs)
run_step(render_target_step, inputs)
run_step(render_mechanism_step, inputs)
run_step(render_target_discovery_step, inputs)
run_step(render_graph_step, inputs)
run_step(render_download_step, inputs)

st.markdown("---")

with st.expander("Supabase evidence database preview"):
    if evidence_df is not None:
        st.write(f"Total evidence records: {len(evidence_df)}")
        st.dataframe(evidence_df, use_container_width=True)
    else:
        st.warning("Could not load Supabase evidence database preview.")
