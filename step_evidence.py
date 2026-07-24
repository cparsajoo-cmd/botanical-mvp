import streamlit as st
import pandas as pd
from research_engine import run_research_engine
from connector_session_observability import build_connector_session_observability


def render_evidence_step(inputs):
    st.markdown("---")
    st.markdown("## Step 2 — Collect online evidence")

    st.caption(
        "This searches live sources for a small number of plants right "
        "now. Full coverage across all plants happens separately and "
        "continuously via the 'Bulk Evidence Collection' page — this "
        "step doesn't need to be exhaustive."
    )

    quick_count = st.slider(
        "Number of plants to search right now",
        min_value=3,
        max_value=30,
        value=8,
        help="Lower = faster. Bulk Evidence Collection covers the rest "
             "of the database in the background, so this can stay small.",
    )

    if st.button("Step 2: Collect online evidence"):
        with st.spinner("Searching sources and saving evidence to Supabase..."):
            research_output = run_research_engine(
                product_type=inputs["product_type"],
                dosage_form=inputs["dosage_form"],
                indication=inputs["indication"],
                target_market=inputs["market"],
                evidence_strictness="Flexible",
                max_results_per_plant=inputs["max_pubmed_results"],
                save=True,
                global_candidate_count=quick_count,
            )

        st.session_state["research_output"] = research_output

    research_output = st.session_state.get("research_output")

    if research_output:
        saved_records = research_output.get("saved_records", [])
        errors = research_output.get("errors", [])
        sources_checked = research_output.get("sources_checked", [])
        candidate_plants = research_output.get("candidate_plants", [])

        st.success(f"{len(saved_records)} online evidence records saved.")

        if sources_checked:
            st.write("**Sources checked:**")
            st.write(", ".join(sorted(set(sources_checked))))

        if candidate_plants:
            st.write("**Candidate plants searched:**")
            st.write(", ".join(candidate_plants))

        if errors:
            st.warning("Some searches produced errors.")
            st.dataframe(pd.DataFrame(errors), width="stretch")

        with st.expander("🔌 Collection Session Status (Sprint 6A.1)"):
            st.caption(
                "This describes ONLY the collection attempt above, in this "
                "session — it is not persistent monitoring, not data "
                "freshness, and not a record of connector health over time. "
                "Nothing here is saved once you leave this page."
            )
            observability = build_connector_session_observability(research_output)
            st.write(f"**Overall session status:** {observability['overall_status']}")

            totals = observability["session_totals"]
            st.write(
                f"Attempted: {totals['sources_attempted']} | "
                f"Completed: {totals['sources_completed']} | "
                f"Completed (no records): {totals['sources_completed_no_records']} | "
                f"Failed: {totals['sources_failed']} | "
                f"Timed out: {totals['sources_timed_out']} | "
                f"Not configured: {totals['sources_not_configured']} | "
                f"Records saved: {totals['records_saved']}"
            )

            connector_rows = [
                {
                    "Connector": c["connector_name"],
                    "Type": c["connector_type"],
                    "Status": c["execution_status"],
                    "Configuration": c["configuration_status"],
                    "Records saved": c["records_saved"],
                    "Cache": c["cache_observability"].split(".")[0] + ".",
                    "Error": c["error_message"] or "",
                }
                for c in observability["connectors"]
            ]
            st.dataframe(pd.DataFrame(connector_rows), width="stretch")

            for lim in observability["limitations"]:
                st.caption(f"⚠️ {lim}")

