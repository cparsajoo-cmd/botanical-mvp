import streamlit as st
import pandas as pd

from target_compound_plant_engine import TargetCompoundPlantEngine


def render_target_discovery_step(inputs):
    knowledge_df = st.session_state.get("knowledge_df")
    ranking_df = st.session_state.get("ranking")

    if knowledge_df is None or knowledge_df.empty:
        return

    st.markdown("---")
    st.markdown("## Step 8.9 — Target → Compound → Plant Discovery")

    st.write(
        "This engine starts from biological targets and mechanisms, then identifies active compounds and candidate plants connected to them."
    )

    if st.button("Step 8.9: Discover target-compound-plant opportunities"):
        with st.spinner("Discovering target → compound → plant opportunities..."):
            engine = TargetCompoundPlantEngine()
            tcp_df = engine.discover(
                knowledge_df=knowledge_df,
                ranking_df=ranking_df,
                inputs=inputs,
            )

        st.session_state["target_compound_plant_df"] = tcp_df

    tcp_df = st.session_state.get("target_compound_plant_df")

    if tcp_df is None:
        return

    if tcp_df.empty:
        st.warning("No target-compound-plant opportunities found yet.")
        return

    st.success(f"{len(tcp_df)} target-compound-plant opportunities found.")

    strong = tcp_df[
        tcp_df["Opportunity_Category"] == "Strong target-to-plant R&D opportunity"
    ]

    promising = tcp_df[
        tcp_df["Opportunity_Category"] == "Promising target-to-plant opportunity"
    ]

    commercial = tcp_df[
        tcp_df["Opportunity_Category"] == "Known commercial mechanism candidate"
    ]

    weak = tcp_df[
        tcp_df["Opportunity_Category"] == "Weak target-to-plant signal"
    ]

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Strong R&D", len(strong))

    with c2:
        st.metric("Promising", len(promising))

    with c3:
        st.metric("Known commercial", len(commercial))

    with c4:
        st.metric("Weak signal", len(weak))

    st.markdown("### A. Strong target-to-plant R&D opportunities")
    st.dataframe(strong, use_container_width=True, hide_index=True)

    st.markdown("### B. Promising target-to-plant opportunities")
    st.dataframe(promising, use_container_width=True, hide_index=True)

    st.markdown("### C. Known commercial mechanism candidates")
    st.dataframe(commercial, use_container_width=True, hide_index=True)

    st.markdown("### D. Weak signals")
    st.dataframe(weak, use_container_width=True, hide_index=True)

    st.markdown("### Full target-compound-plant discovery table")
    st.dataframe(tcp_df, use_container_width=True, hide_index=True)

    csv = tcp_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download target-compound-plant discovery as CSV",
        data=csv,
        file_name="target_compound_plant_discovery.csv",
        mime="text/csv",
    )
