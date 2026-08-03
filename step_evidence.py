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
        reference_seeds = research_output.get(
            "reference_seed_plants",
            research_output.get("candidate_discovery_diagnostics", {}).get(
                "seed_plants_before_discovery", []
            ),
        )
        # candidate_records (added alongside candidate_selection_diagnostics)
        # carries a per-plant evidence_status. When present, "directly
        # supported" (validated_direct: clinical/systematic-review
        # literature) and "indirectly supported" (validated_indirect:
        # weaker literature signal) are shown separately -- they are never
        # collapsed into one undifferentiated "Literature-validated" label,
        # since the strength of support differs scientifically. Older
        # research_output dictionaries have no candidate_records key and
        # fall back to the previous combined list under cautious umbrella
        # wording instead.
        candidate_records = research_output.get("candidate_records") or []
        directly_supported = [
            record["name"] for record in candidate_records
            if record.get("evidence_status") == "validated_direct"
        ]
        indirectly_supported = [
            record["name"] for record in candidate_records
            if record.get("evidence_status") == "validated_indirect"
        ]

        if reference_seeds:
            st.caption("Reference/database seeds (not yet validated for this indication): " + ", ".join(reference_seeds))
        if candidate_records:
            if directly_supported:
                st.caption("Directly supported (clinical/systematic-review literature): " + ", ".join(directly_supported))
            if indirectly_supported:
                st.caption("Indirectly supported (weaker literature signal): " + ", ".join(indirectly_supported))
        elif evidence_backed:
            # Backward compatibility: older research_output has no
            # per-candidate evidence_status breakdown to split on.
            st.caption("Literature-supported/discovered: " + ", ".join(evidence_backed))
        if discovered:
            st.caption("Newly discovered from literature: " + ", ".join(discovered))

        diagnostics = research_output.get("candidate_discovery_diagnostics", {}) or {}
        selection_diagnostics = (
            research_output.get("candidate_selection_diagnostics")
            or diagnostics.get("candidate_selection_diagnostics")
            or {}
        )

        # Production-facing shortlist audit.  It shows how many candidates came
        # from each origin (reference seed, literature validation, ranked
        # fallback) and makes the final selection traceable without exposing
        # raw implementation details. Old research_output dicts (produced
        # before this diagnostics upgrade) fall back to their previous
        # fields automatically.
        st.markdown("### 🌿 Candidate shortlist audit")
        requested = diagnostics.get("requested_candidate_count", quick_count)
        seed_list = diagnostics.get("seed_plants_before_discovery", reference_seeds)
        discovered_list = diagnostics.get("online_discovered_plants", discovered)
        fallback_list = diagnostics.get("fallback_ranked_plants", [])
        final_list = diagnostics.get("final_candidate_plants", candidate_plants)
        shortfall = diagnostics.get(
            "candidate_shortfall",
            max(0, int(requested or 0) - len(final_list or [])),
        )
        shortfall_reason = diagnostics.get(
            "shortfall_reason", selection_diagnostics.get("shortfall_reason", "none")
        )

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Requested", int(requested or 0))
        c2.metric("Reference seeds", len(seed_list or []))
        # This is the RAW discovery count (online_discovered_plants) -- it
        # is deliberately NOT labelled as a validated count. Directly vs.
        # indirectly SUPPORTED counts (computed from candidate_records,
        # which carry a real per-plant evidence_status) are shown
        # separately below whenever candidate_records is available.
        c3.metric("Literature-discovered candidates", len(discovered_list or []))
        c4.metric("Final candidates", len(final_list or []))
        c5.metric("Collection completed", diagnostics.get("collection_completed_plant_count", 0))

        if candidate_records:
            d1, d2 = st.columns(2)
            d1.metric("Directly supported", len(directly_supported))
            d2.metric("Indirectly supported", len(indirectly_supported))

        if shortfall:
            st.error(
                f"Candidate shortfall: {shortfall}. The app requested "
                f"{requested} plants but only {len(final_list or [])} scientifically "
                f"plausible candidates were found (reason: {shortfall_reason})."
            )
        else:
            st.success("The requested candidate count reached the collection loop.")

        st.write("**1. Reference/database seed plants** _(not yet indication-validated)_")
        st.write(", ".join(seed_list) if seed_list else "None")
        st.write("**2. Literature-discovered candidates**")
        if candidate_records:
            st.write(
                "_Directly supported (clinical/systematic-review literature):_ "
                + (", ".join(directly_supported) if directly_supported else "None")
            )
            st.write(
                "_Indirectly supported (weaker literature signal):_ "
                + (", ".join(indirectly_supported) if indirectly_supported else "None")
            )
        else:
            # Backward compatibility: no per-candidate evidence_status
            # breakdown available for this research_output shape. This is
            # the RAW discovery list -- not asserted here as validated.
            st.caption("Raw discovery count; per-candidate support level not available for this session.")
            st.write(", ".join(discovered_list) if discovered_list else "None")
        st.write("**3. Ranked fallback candidates available**")
        st.write(", ".join(fallback_list) if fallback_list else "None")
        st.write("**4. Final plants sent to evidence collectors**")
        st.write(", ".join(final_list) if final_list else "None")

        st.write("**Discovery and selection counters**")
        st.json({
            "generic_queries_attempted": diagnostics.get("queries_attempted", 0),
            "generic_records_retrieved": diagnostics.get("records_retrieved", 0),
            "unique_records": diagnostics.get("unique_records", 0),
            "plant_catalogue_size": diagnostics.get("catalogue_size", 0),
            "candidate_pool_size": diagnostics.get("candidate_pool_size", 0),
            "focused_queries_attempted": diagnostics.get("candidate_queries_attempted", 0),
            "candidate_validation_records": diagnostics.get("candidate_validation_records", 0),
            "generic_discovery_pool_count": diagnostics.get("generic_discovery_count", 0),
            "focused_candidates_validated": diagnostics.get("candidate_validated_count", 0),
            "combined_discovery_pool_count": diagnostics.get("discovery_candidate_pool_count", 0),
            "selected_discovery_count": len(diagnostics.get("selected_discovery_candidates", []) or []),
            "excluded_discovery_count": len(diagnostics.get("excluded_discovery_candidates", []) or []),
            "connector_error_count": len(diagnostics.get("connector_errors", []) or []),
        })

        connector_errors = diagnostics.get("connector_errors", []) or []
        if connector_errors:
            st.warning("Discovery connector errors")
            st.code("\n".join(str(item) for item in connector_errors))

        ranked_matches = diagnostics.get("ranked_matches", {}) or {}
        if ranked_matches:
            rows = []
            for plant, meta in ranked_matches.items():
                selected_discovery = set(diagnostics.get("selected_discovery_candidates", []) or [])
                rows.append({
                    "Plant": plant,
                    "Shortlist status": "Selected" if plant in selected_discovery else "Not selected",
                    "Quality-adjusted score": meta.get("score"),
                    "Supporting records": meta.get("supporting_records"),
                    "Human/clinical": meta.get("clinical_human_records", 0),
                    "Systematic reviews": meta.get("systematic_review_records", 0),
                    "Title mentions": meta.get("title_supporting_records"),
                    "Dosage-form support": meta.get("dosage_form_records", 0),
                    "Regulatory mentions": meta.get("regulatory_records", 0),
                    "Preclinical": meta.get("preclinical_records", 0),
                    "Safety signals": meta.get("safety_signal_records", 0),
                    "Matched aliases": ", ".join(meta.get("matched_aliases", [])),
                })
            ranked_df = pd.DataFrame(rows)
            if not ranked_df.empty and "Quality-adjusted score" in ranked_df.columns:
                ranked_df["Quality-adjusted score"] = pd.to_numeric(
                    ranked_df["Quality-adjusted score"], errors="coerce"
                ).fillna(0)
                ranked_df = ranked_df.sort_values(
                    ["Quality-adjusted score", "Human/clinical", "Systematic reviews"],
                    ascending=[False, False, False],
                )
                ranked_df.insert(0, "Rank", range(1, len(ranked_df) + 1))
            st.write("**Quality-ranked discovery pool**")
            st.caption(
                "Candidates are ranked before the requested shortlist is filled. This is a "
                "transparent discovery-priority score, not a final efficacy claim. "
                "Human/clinical and systematic-review signals receive more weight than "
                "preclinical mentions; dosage-form fit and regulatory mentions also contribute."
            )
            st.dataframe(ranked_df, width="stretch")

        with st.expander("Raw candidate discovery diagnostics"):
            st.json(diagnostics)

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

