import streamlit as st
import pandas as pd
from global_plant_discovery_engine import GlobalPlantDiscoveryEngine


def render_discovery_step(inputs):
    st.markdown("---")
    st.markdown("## Step 3 — Global AI discovery test")

    if st.button("Step 3: Test global discovery engine"):
        with st.spinner("Searching global discovery sources..."):
            engine = GlobalPlantDiscoveryEngine()
            discovery_result = engine.discover(
                therapeutic_area=inputs["indication"],
                dosage_form=inputs["dosage_form"],
                target_market=inputs["market"],
            )

        st.session_state["discovery_result"] = discovery_result

    discovery_result = st.session_state.get("discovery_result")

    if discovery_result:
        if discovery_result.get("question") is None:
            st.warning("No question profile found.")
        else:
            st.success("Global discovery completed.")

            st.write("**Sources used:**")
            st.write(", ".join(discovery_result.get("sources", [])))

            col_a, col_b, col_c, col_d = st.columns(4)

            with col_a:
                st.metric("Plants found", len(discovery_result.get("candidate_plants", [])))
            with col_b:
                st.metric("Compounds found", len(discovery_result.get("compounds", [])))
            with col_c:
                st.metric("Papers found", len(discovery_result.get("papers", [])))
            with col_d:
                st.metric("Clinical trials", len(discovery_result.get("clinical_trials", [])))

            st.markdown("### Candidate plants")
            st.dataframe(
                pd.DataFrame(discovery_result.get("candidate_plants", [])),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### Compounds")
            st.dataframe(
                pd.DataFrame(discovery_result.get("compounds", [])),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### Papers")
            st.dataframe(
                pd.DataFrame(discovery_result.get("papers", [])),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("### Clinical trials")
            st.dataframe(
                pd.DataFrame(discovery_result.get("clinical_trials", [])),
                use_container_width=True,
                hide_index=True,
            )
