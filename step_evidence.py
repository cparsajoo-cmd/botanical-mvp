import streamlit as st
import pandas as pd
from research_engine import run_research_engine
from connector_session_observability import build_connector_session_observability
from telemetry_persistence import persist_connector_telemetry


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

    # Task 6 — pilot-scope evidence coverage. Off by default (no change
    # to the default session's behavior/coverage/cost). When checked,
    # every source's per-plant result ceiling is raised to
    # source_registry.PILOT_MAX_RESULTS for this collection run — see
    # research_engine.run_research_engine's pilot_mode parameter.
    pilot_mode = st.checkbox(
        "Pilot-scope coverage (fuller evidence collection for a paid deliverable)",
        value=False,
        help="Raises the per-source result ceiling for this collection "
             "run only — intended for a scoped pilot deliverable, not "
             "routine exploratory sessions.",
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
                pilot_mode=pilot_mode,
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

        evidence_backed = research_output.get("evidence_backed_plants", [])
        discovered = research_output.get("online_discovered_plants", [])
        if evidence_backed:
            st.caption("Evidence-backed seeds: " + ", ".join(evidence_backed))
        if discovered:
            st.caption("Newly discovered from literature: " + ", ".join(discovered))

        diagnostics = research_output.get("candidate_discovery_diagnostics", {})
        if diagnostics:
            with st.expander("Candidate discovery diagnostics"):
                st.write(
                    f"Generic queries: {diagnostics.get('queries_attempted', 0)} | "
                    f"Generic records: {diagnostics.get('records_retrieved', 0)} | "
                    f"Unique records: {diagnostics.get('unique_records', 0)} | "
                    f"Plant catalogue size: {diagnostics.get('catalogue_size', 0)}"
                )
                st.write(
                    f"Candidate pool: {diagnostics.get('candidate_pool_size', 0)} | "
                    f"Focused candidate queries: "
                    f"{diagnostics.get('candidate_queries_attempted', 0)} | "
                    f"Candidate validation records: "
                    f"{diagnostics.get('candidate_validation_records', 0)} | "
                    f"Validated candidates added: "
                    f"{diagnostics.get('candidate_validated_count', 0)}"
                )
                st.write("**Therapeutic query terms:**")
                st.write(", ".join(diagnostics.get("query_terms", [])))

                ranked_matches = diagnostics.get("ranked_matches", {})
                if ranked_matches:
                    rows = []
                    for plant, meta in ranked_matches.items():
                        rows.append({
                            "Plant": plant,
                            "Score": meta.get("score"),
                            "Supporting records": meta.get("supporting_records"),
                            "Title mentions": meta.get("title_supporting_records"),
                            "Matched aliases": ", ".join(meta.get("matched_aliases", [])),
                        })
                    st.dataframe(pd.DataFrame(rows), width="stretch")

                connector_errors = diagnostics.get("connector_errors", [])
                if connector_errors:
                    st.warning("Some discovery queries failed.")
                    st.write("\n".join(f"- {item}" for item in connector_errors))

        if errors:
            st.warning("Some searches produced errors.")
            st.dataframe(pd.DataFrame(errors), width="stretch")

        with st.expander("🔌 Collection Session Status (Sprint 6A.1)"):
            st.caption(
                "This describes ONLY the collection attempt above, in this "
                "session — it is not persistent monitoring, not data "
                "freshness, and not a record of connector health over time. "
                "This information is held only in the current application "
                "session. It is not persisted to the database and may be "
                "lost when the application session ends or the application "
                "restarts."
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
                    "Errors": f"{c['error_count']} — " + "; ".join(c["error_messages"]) if c["error_count"] else "",
                }
                for c in observability["connectors"]
            ]
            st.dataframe(pd.DataFrame(connector_rows), width="stretch")

            for lim in observability["limitations"]:
                st.caption(f"⚠️ {lim}")

            # Sprint 6A.2 — best-effort persistence of the observability
            # object above. Never blocks or interrupts this page; only a
            # minimal status message is shown, per this Sprint's explicit
            # UI constraint (no database/SQL details exposed here).
            telemetry_summary = persist_connector_telemetry(observability)
            if telemetry_summary["status"] == "persisted":
                st.caption("✅ Telemetry persisted successfully")
            else:
                st.caption("ℹ️ Telemetry persistence unavailable")

