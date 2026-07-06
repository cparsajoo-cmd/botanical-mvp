import streamlit as st
from botanical_knowledge_graph_engine import build_graph_from_ranking


def render_graph_step(inputs):
    ranking = st.session_state.get("ranking")

    if ranking is None or ranking.empty:
        return

    st.markdown("---")
    st.markdown("## Step 9 — Build Botanical Knowledge Graph")

    st.write(
        "This stores plant–compound–target–indication relationships into Supabase graph tables."
    )

    if st.button("Step 9: Build Knowledge Graph from ranking"):
        with st.spinner("Building botanical knowledge graph..."):
            edge_count = build_graph_from_ranking(
                ranking_df=ranking,
                indication=inputs["indication"],
            )

        st.success(f"{edge_count} graph relations saved.")
