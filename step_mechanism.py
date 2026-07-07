import streamlit as st
import pandas as pd

from mechanism_discovery_engine import MechanismDiscoveryEngine


def render_mechanism_step(inputs):
    knowledge_df = st.session_state.get("knowledge_df")

    if knowledge_df is None or knowledge_df.empty:
        return

    st.markdown("---")
    st.markdown("## Step 8.8 — Mechanism Discovery Engine")

    st.write(
        "This engine uses extracted scientific knowledge to find new R&D candidates sharing targets, mechanisms, or indications."
    )

    if st.button("Step 8.8: Discover mechanism-based R&D candidates"):
        with st.spinner("Searching mechanism-based R&D opportunities..."):
            engine = MechanismDiscoveryEngine()
            mechanism_df = engine.discover(
                knowledge_df=knowledge_df,
                inputs=inputs,
            )

        st.session_state["mechanism_df"] = mechanism_df

    mechanism_df = st.session_state.get("mechanism_df")

    if mechanism_df is None:
        return

    if mechanism_df.empty:
        st.warning("No mechanism-based R&D candidates found yet.")

        with st.expander("Debug: extracted knowledge available"):
            st.write("Knowledge columns:")
            st.write(list(knowledge_df.columns))
            st.write("Knowledge rows:", len(knowledge_df))
            st.dataframe(knowledge_df.head(20), use_container_width=True, hide_index=True)

        return

    st.success(f"{len(mechanism_df)} mechanism-based R&D opportunities found.")

    strong = mechanism_df[
        mechanism_df["Mechanism_Category"] == "Strong mechanism-based R&D candidate"
    ]

    promising = mechanism_df[
        mechanism_df["Mechanism_Category"] == "Promising mechanism-based candidate"
    ]

    weak = mechanism_df[
        mechanism_df["Mechanism_Category"] == "Weak mechanism signal"
    ]

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("Strong mechanism candidates", len(strong))

    with c2:
        st.metric("Promising candidates", len(promising))

    with c3:
        st.metric("Weak signal", len(weak))

    st.markdown("### A. Strong mechanism-based R&D candidates")
    st.dataframe(strong, use_container_width=True, hide_index=True)

    st.markdown("### B. Promising mechanism-based candidates")
    st.dataframe(promising, use_container_width=True, hide_index=True)

    st.markdown("### C. Weak mechanism signals")
    st.dataframe(weak, use_container_width=True, hide_index=True)

    st.markdown("### Full mechanism discovery table")
    st.dataframe(mechanism_df, use_container_width=True, hide_index=True)

    csv = mechanism_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download mechanism discovery as CSV",
        data=csv,
        file_name="mechanism_discovery.csv",
        mime="text/csv",
    )
