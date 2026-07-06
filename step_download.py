import streamlit as st


def render_download_step():
    ranking = st.session_state.get("ranking")

    if ranking is None or ranking.empty:
        return

    st.markdown("---")
    st.markdown("## Step 10 — Download unified ranking")

    csv = ranking.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download unified R&D ranking as CSV",
        data=csv,
        file_name="unified_rd_discovery_ranking.csv",
        mime="text/csv",
    )
