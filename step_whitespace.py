import streamlit as st
import pandas as pd

from white_space_discovery_engine import WhiteSpaceDiscoveryEngine


def render_whitespace_step(inputs):
    ranking = st.session_state.get("ranking")

    if ranking is None or ranking.empty:
        return

    st.markdown("---")
    st.markdown("## Step 8.6 — White-space Discovery Engine")

    st.write(
        "This engine searches for new R&D plant candidates connected to active compounds already identified in the ranking."
    )

    if st.button("Step 8.6: Discover white-space R&D candidates"):
        with st.spinner("Searching white-space plant-compound opportunities..."):
            engine = WhiteSpaceDiscoveryEngine()
            white_space_df = engine.discover(
                ranking_df=ranking,
                inputs=inputs,
            )

        st.session_state["white_space_df"] = white_space_df

    white_space_df = st.session_state.get("white_space_df")

    if white_space_df is None:
        return

    if white_space_df.empty:
        st.warning("No white-space candidates found yet.")
        return

    st.success(f"{len(white_space_df)} white-space R&D opportunities found.")

    strong = white_space_df[
        white_space_df["White_Space_Category"] == "Strong white-space R&D candidate"
    ]

    exploratory = white_space_df[
        white_space_df["White_Space_Category"] == "Promising exploratory R&D candidate"
    ]

    weak = white_space_df[
        white_space_df["White_Space_Category"] == "Weak white-space signal"
    ]

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Strong white-space", len(strong))

    with c2:
        st.metric("Exploratory R&D", len(exploratory))

    with c3:
        st.metric("Weak signal", len(weak))

    st.markdown("### A. Strong white-space R&D candidates")
    st.dataframe(strong, use_container_width=True, hide_index=True)

    st.markdown("### B. Promising exploratory R&D candidates")
    st.dataframe(exploratory, use_container_width=True, hide_index=True)

    st.markdown("### C. Weak white-space signals")
    st.dataframe(weak, use_container_width=True, hide_index=True)

    st.markdown("### Full white-space discovery table")
    st.dataframe(white_space_df, use_container_width=True, hide_index=True)

    csv = white_space_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download white-space discovery as CSV",
        data=csv,
        file_name="white_space_discovery.csv",
        mime="text/csv",
    )
