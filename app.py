import streamlit as st

from step_inputs import render_inputs
from step_question import render_question_step
from step_seed import render_seed_step
from step_discovery import render_discovery_step
from step_evidence import render_evidence_step
from step_ranking import render_ranking_step
from step_opportunity import render_opportunity_step
from step_market import render_market_step
from step_whitespace import render_whitespace_step
from step_knowledge import render_knowledge_step
from step_mechanism import render_mechanism_step
from step_graph import render_graph_step
from step_download import render_download_step
from evidence_database import load_evidence_database


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide",
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("AI Botanical R&D Discovery Platform")


inputs = render_inputs()

render_question_step(inputs)
render_seed_step()
render_discovery_step(inputs)
render_evidence_step(inputs)
render_ranking_step(inputs)
render_opportunity_step()
render_market_step()
render_whitespace_step(inputs)
render_knowledge_step(inputs)
render_mechanism_step(inputs)
render_graph_step(inputs)
render_download_step()


st.markdown("---")

with st.expander("Supabase evidence database preview"):
    try:
        df = load_evidence_database()
        st.write(f"Total evidence records: {len(df)}")
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning("Could not load Supabase evidence database preview.")
        st.write(str(e))
