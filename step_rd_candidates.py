import pandas as pd
import streamlit as st

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from pharma_report_generator import generate_pharma_report
from product_development_concept import add_development_concept_column
from candidate_output_adapter import validate_result_df
from candidate_shortlisting import build_plant_candidate_shortlist
from sensitivity_display_adapter import prepare_sensitivity_payload
from decision_record_persistence import persist_decision_record
from standard_evidence_builder import (
    build_scientific_evidence_presentation_payload,
    get_scientific_evidence_by_ids,
)


def _unique_nonempty(values):
    seen = set()
    out = []
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() == "nan":
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _join_unique(values, limit=8):
    """Compact, deterministic aggregation for Step 4 plant summaries."""
    items = _unique_nonempty(values)
    if not items:
        return ""
    shown = items[:limit]
    suffix = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return "; ".join(shown) + suffix


def _build_scientific_plant_summary(inventory_df, regulatory_df=None):
    """Create one truthful summary row per plant without discarding detail.

    The detailed plant-compound table remains available separately and is the
    source for the full CSV export.  This summary only aggregates values that
    are already present in the inventory; it does not infer efficacy.
    """
    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        return pd.DataFrame()

    rows = []
    for plant, group in inventory_df.groupby("Known_Plant", sort=False):
        compound_values = _unique_nonempty(group.get("Known_Compound", []))
        target_values = _unique_nonempty(group.get("Known_Target", []))
        mechanism_values = _unique_nonempty(group.get("Known_Mechanism", []))
        reference_values = _unique_nonempty(group.get("Reference_URL", []))
        rows.append({
            "Plant": plant,
            "Compound_Count": len(compound_values),
            "Known_Compounds": _join_unique(compound_values, 6),
            "Target_Count": len(target_values),
            "Known_Targets": _join_unique(target_values, 6),
            "Known_Mechanisms": _join_unique(mechanism_values, 6),
            "Evidence_Levels": _join_unique(group.get("Evidence_Level", []), 5),
            "Plant_Parts": _join_unique(group.get("Known_Plant_Part", []), 5),
            "Extraction_Methods": _join_unique(group.get("Typical_Extraction", []), 5),
            "Dosage_Forms": _join_unique(group.get("Dosage_Form", []), 5),
            "Safety_Notes": _join_unique(group.get("Safety_Note", []), 4),
            "Toxicity_Notes": _join_unique(group.get("Toxicity", []), 4),
            "Reference_Count": len(reference_values),
        })

    summary_df = pd.DataFrame(rows)

    if isinstance(regulatory_df, pd.DataFrame) and not regulatory_df.empty and "Plant" in regulatory_df.columns:
        regulatory_cols = [
            c for c in [
                "Plant", "EMA_HMPC_Status", "WHO_Status", "ESCOP_Status",
                "US_Status", "UK_Status"
            ] if c in regulatory_df.columns
        ]
        if len(regulatory_cols) > 1:
            reg = regulatory_df[regulatory_cols].drop_duplicates(subset=["Plant"])
            summary_df = summary_df.merge(reg, on="Plant", how="left")

    return summary_df


def _get_evidence_df():
    evidence_df = st.session_state.get("evidence_df")
    if isinstance(evidence_df, pd.DataFrame):
        return evidence_df
    return None


def _get_step2_candidate_shortlist():
    """Return the final candidate shortlist produced by Step 2.

    Step 3 must analyse the same candidates that were actually sent through
    the Step 2 evidence-collection loop.  Older code rebuilt a fresh, broad
    indication inventory here, which could replace an 8-plant shortlist with
    dozens of unrelated catalogue plants.

    The research output is the authoritative source.  The evidence dataframe
    is only a compatibility fallback for sessions created by older versions.
    """
    research_output = st.session_state.get("research_output")
    if isinstance(research_output, dict):
        candidates = _unique_nonempty(research_output.get("candidate_plants", []))
        if candidates:
            return candidates, "Step 2 final shortlist"

        diagnostics = research_output.get("candidate_discovery_diagnostics") or {}
        if isinstance(diagnostics, dict):
            candidates = _unique_nonempty(diagnostics.get("final_candidate_plants", []))
            if candidates:
                return candidates, "Step 2 diagnostic shortlist"

    evidence_df = _get_evidence_df()
    if isinstance(evidence_df, pd.DataFrame) and not evidence_df.empty:
        for column in ("plant", "Plant", "scientific_name", "Scientific_Name"):
            if column in evidence_df.columns:
                candidates = _unique_nonempty(evidence_df[column].tolist())
                if candidates:
                    return candidates, "Step 2 evidence records"

    return [], "unavailable"


def _collect_evidence_record_ids(result_df):
    """Task 13.2C — the union of every candidate row's own
    Applicability_Summary.evidence_record_ids (Task 10.2), deduplicated,
    order-preserving. Read-only over `result_df` — never touches the
    engine, evidence_df, or the database itself; this only decides
    WHICH ids to later ask standard_evidence_builder.
    get_scientific_evidence_by_ids() to resolve.

    A row with no "Applicability_Summary" column at all, a None value,
    or any non-dict value simply contributes nothing — never an error,
    matching the same degrade-safely discipline
    build_applicability_traceability() already established for reading
    this same field in pharma_report_generator.py.
    """
    ids = []
    seen = set()
    if not isinstance(result_df, pd.DataFrame) or "Applicability_Summary" not in result_df.columns:
        return ids
    for summary in result_df["Applicability_Summary"]:
        if not isinstance(summary, dict):
            continue
        for record_id in summary.get("evidence_record_ids") or []:
            if record_id is None or record_id in seen:
                continue
            seen.add(record_id)
            ids.append(record_id)
    return ids


# ---------------------------------------------------------------------- #
# Cache the raw Supabase table fetches. plant_compounds went from ~850
# rows to 50,000+ after the Dr. Duke's import — refetching that whole
# table over the network every single time a button is clicked (and this
# file previously built TWO separate engines per Step 3 click, so TWO
# full refetches) is what made Step 3 hang/stall. Caching it means the
# network fetch happens once per session (or until ttl expires), and every
# engine built afterwards reuses the same in-memory DataFrame — engine
# construction itself (grouping ~50k rows by scientific_name) is a fast,
# local pandas operation once the network fetch is out of the picture.
# ---------------------------------------------------------------------- #

@st.cache_data(ttl=600, show_spinner=False)
def _cached_plant_compounds_df():
    """Returns (df, succeeded). succeeded=False means the load itself
    failed (network/auth/schema error) — NOT that the query legitimately
    returned zero rows. Previously this silently returned an empty
    DataFrame on ANY failure, indistinguishable from "no data exists" —
    flagged in external review as a fail-silent risk (no way to tell a
    real outage from real absence of data) feeding directly into a
    second risk: nothing downstream knew to be more cautious about a
    recommendation built on data that may not have actually loaded.
    See BotanicalRDCandidateEngine's data_source_reliable parameter and
    structured_rationale.go_investigate_hold_no_go's fallback_occurred
    parameter for what this now feeds into."""
    from supabase_data import load_plant_compounds_df
    try:
        return load_plant_compounds_df(), True
    except Exception:
        return pd.DataFrame(), False


@st.cache_data(ttl=600, show_spinner=False)
def _cached_compound_profiles_df():
    """See _cached_plant_compounds_df's docstring — same (df, succeeded) contract."""
    from supabase_data import load_compound_profiles_df
    try:
        return load_compound_profiles_df(), True
    except Exception:
        return pd.DataFrame(), False


@st.cache_data(ttl=600, show_spinner=False)
def _cached_scientific_evidence_df():
    """See _cached_plant_compounds_df's docstring — same (df, succeeded) contract."""
    from supabase_data import load_scientific_evidence_df
    try:
        return load_scientific_evidence_df(), True
    except Exception:
        return pd.DataFrame(), False


# Building the engine itself is the expensive part now — with 50,000+
# plant_compounds rows, __init__ groups every row by scientific_name and
# builds a deduplicated dict per plant (~2,200 plants). That grouping work
# was happening from scratch on every single button click. Caching the
# constructed ENGINE (not just the raw table) means that grouping happens
# once per `use_live_search` value and is then reused.
#
# evidence_df (from live Step 2 searches, stored in session state) is kept
# out of the *hashed* argument (it's still underscore-prefixed, since
# Streamlit can't hash a DataFrame directly) but its CONTENT now feeds the
# cache key via `evidence_fingerprint` below. Previously evidence_df was
# excluded from the cache key entirely, so a fresh Step 2 run could sit
# unused in a stale cached engine for up to `ttl` seconds. Fingerprinting
# is deliberately cheap (row count + a vectorized content hash) rather
# than hashing the whole DataFrame structurally, since this data is
# usually small (a handful of live-search results per session).
def _evidence_fingerprint(evidence_df):
    if evidence_df is None or evidence_df.empty:
        return ("empty", 0)
    try:
        content_hash = int(pd.util.hash_pandas_object(evidence_df, index=True).sum())
    except Exception:
        # If hashing ever fails on some exotic column dtype, fall back to
        # row count alone — still catches the common "Step 2 just added
        # N new rows" case, just not an in-place content edit.
        content_hash = 0
    return (len(evidence_df), content_hash)


ENGINE_CACHE_VERSION = "step4_scientific_inventory_v2"


@st.cache_resource(ttl=120, show_spinner=False)
def _cached_engine(
    use_live_search: bool,
    evidence_fingerprint,
    engine_cache_version: str,
    _evidence_df=None,
):
    plant_compounds_df, plant_compounds_ok = _cached_plant_compounds_df()
    compound_profiles_df, compound_profiles_ok = _cached_compound_profiles_df()
    scientific_evidence_df, scientific_evidence_ok = _cached_scientific_evidence_df()

    return BotanicalRDCandidateEngine(
        evidence_df=_evidence_df,
        use_live_search=use_live_search,
        plant_compounds_df=plant_compounds_df,
        compound_profiles_df=compound_profiles_df,
        scientific_evidence_df=scientific_evidence_df,
        # Review #17: if any core Supabase load actually FAILED (not
        # just legitimately returned few/no rows), the engine caps
        # every recommendation at "Investigate" — a Go call must never
        # be issued on data that may not have actually loaded.
        data_source_reliable=plant_compounds_ok and compound_profiles_ok and scientific_evidence_ok,
    )


def _build_engine(evidence_df, use_live_search):
    fingerprint = _evidence_fingerprint(evidence_df)
    return _cached_engine(
        use_live_search,
        fingerprint,
        ENGINE_CACHE_VERSION,
        _evidence_df=evidence_df,
    )


def _offline_engine():
    return _build_engine(_get_evidence_df(), use_live_search=False)


# Display/loop safety cap. With Dr. Duke's data, "known plants" for a
# broad indication can run into the hundreds or low thousands — rendering
# that as one long joined string, or running market_landscape_df across
# all of them, is what makes the page feel unresponsive. Showing/scoring
# the first N is enough to be useful; nothing below silently drops data,
# it only limits what's displayed/probed by these two exploratory steps.
_MAX_MARKET_CHECK_PLANTS = 30


def _recommendation_block(result_df):
    if result_df is None or not isinstance(result_df, pd.DataFrame) or result_df.empty:
        st.warning("Run Step 5 first, then generate the final recommendation.")
        return

    df = result_df.copy()

    if "R&D_Opportunity_Score" in df.columns:
        df["R&D_Opportunity_Score"] = pd.to_numeric(
            df["R&D_Opportunity_Score"], errors="coerce"
        ).fillna(0)
        df = df.sort_values("R&D_Opportunity_Score", ascending=False)

    plant_col = "Alternative_Plant" if "Alternative_Plant" in df.columns else df.columns[0]
    decision_col = "Decision_Class" if "Decision_Class" in df.columns else None

    best_rows = df.drop_duplicates(subset=[plant_col], keep="first")

    recommended = best_rows
    if decision_col:
        recommended = best_rows[
            best_rows[decision_col].astype(str).str.contains(
                "strong|promising|recommend", case=False, na=False
            )
        ]
        if recommended.empty:
            recommended = best_rows.head(5)

    display_cols = [
        col for col in [
            "Alternative_Plant",
            "Shared_or_Similar_Compound",
            "Target_or_Mechanism",
            "R&D_Opportunity_Score",
            "Decision_Class",
            "Safety_Flags",
            "Market_Status",
            "Novelty_Status",
            "Rationale",
        ] if col in recommended.columns
    ]

    st.markdown("### ✅ Recommended / worth validating")
    st.caption(
        "\"Recommended\" means worth a human researcher's time to check, based "
        "on chemical hypothesis + whatever evidence was found — it is not a "
        "certification of efficacy. See `Decision_Class` and `Evidence_Level` "
        "in each row for how strong the underlying basis actually is."
    )
    st.dataframe(recommended[display_cols].head(10), width="stretch")

    if decision_col:
        weak = best_rows[
            best_rows[decision_col].astype(str).str.contains(
                "weak|reject|not", case=False, na=False
            )
        ]
        if not weak.empty:
            st.markdown("### 🔴 Weak / not recommended")
            st.dataframe(weak[display_cols].head(10), width="stretch")


def render_rd_candidates_step(inputs):
    indication = inputs.get("indication", "")
    dosage_form = inputs.get("dosage_form", "")
    market = inputs.get("market", "")

    st.markdown("---")
    st.markdown("## Step 3 — Market & Competitive Landscape")

    st.caption(
        "Check what already exists in the market: existing botanical products, "
        "known plants, regulatory status, patent readiness, retail/brand search readiness, "
        "and market saturation signals."
    )

    live_market = st.checkbox(
        "Include live patent / retail search if API keys are configured",
        value=False,
        help="Keep this off unless external API keys are configured.",
        key="rd_market_live_checkbox",
    )

    if st.button("Run Market Analysis", type="primary", key="run_step1_market"):
        try:
            shortlist, shortlist_source = _get_step2_candidate_shortlist()

            # Keep the broad indication inventory only as secondary context.
            # It is useful for Step 4/5 and for showing the size of the wider
            # landscape, but it must not replace the Step 2 shortlist used for
            # the main market analysis.
            with st.spinner("Loading broader indication inventory..."):
                offline_engine = _offline_engine()
                inventory_df = offline_engine.known_inventory_df(indication)

            broader_plants = (
                _unique_nonempty(inventory_df.get("Known_Plant", []))
                if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty
                else []
            )

            st.session_state["rd_inventory_df_internal"] = inventory_df
            st.session_state["rd_broader_market_context_plants"] = broader_plants
            st.session_state["rd_broader_market_context_total"] = len(broader_plants)

            if shortlist:
                market_plants = shortlist[:_MAX_MARKET_CHECK_PLANTS]
                source_label = shortlist_source
            else:
                # Compatibility fallback for users who enter Step 3 without
                # running Step 2 in the current session.  It is explicit in the
                # UI so a broad inventory can never silently masquerade as the
                # Step 2 shortlist.
                market_plants = broader_plants[:_MAX_MARKET_CHECK_PLANTS]
                source_label = "broader indication inventory fallback"

            st.session_state["rd_known_plants"] = market_plants
            st.session_state["rd_known_plants_total"] = len(market_plants)
            st.session_state["rd_market_input_source"] = source_label

            if not market_plants:
                st.session_state["rd_market_landscape_df"] = pd.DataFrame()
                st.warning(
                    "No Step 2 candidate shortlist or broader indication inventory "
                    "was available. Run Step 2 first, then retry Market Analysis."
                )
            else:
                market_engine = _build_engine(
                    _get_evidence_df(), use_live_search=live_market
                )

                with st.spinner(
                    f"Checking market and competitive landscape for "
                    f"{len(market_plants)} shortlisted plant(s)..."
                ):
                    landscape_df = market_engine.market_landscape_df(market_plants)

                st.session_state["rd_market_landscape_df"] = landscape_df
                st.success("✅ Market analysis completed.")

        except Exception as e:
            st.error(f"Market analysis failed: {e}")

    known_plants = st.session_state.get("rd_known_plants", [])
    known_plants_total = st.session_state.get("rd_known_plants_total", len(known_plants))
    market_input_source = st.session_state.get("rd_market_input_source", "")
    broader_plants = st.session_state.get("rd_broader_market_context_plants", [])
    broader_total = st.session_state.get(
        "rd_broader_market_context_total", len(broader_plants)
    )
    landscape_df = st.session_state.get("rd_market_landscape_df")

    if known_plants:
        if "fallback" in str(market_input_source).lower():
            st.warning(
                "Step 2 shortlist was unavailable, so this run used the broader "
                "indication inventory. Run Step 2 and rerun Market Analysis for "
                "shortlist-aligned results."
            )

        st.write(
            f"**Step 2 candidates used for primary market analysis** "
            f"({len(known_plants)} plant(s); source: {market_input_source}):"
        )
        st.write(", ".join(known_plants))

    if broader_plants:
        shortlist_keys = {str(x).strip().lower() for x in known_plants}
        context_only = [
            plant for plant in broader_plants
            if str(plant).strip().lower() not in shortlist_keys
        ]
        with st.expander(
            f"Broader market context — {broader_total} indication-linked plant(s)",
            expanded=False,
        ):
            st.caption(
                "Context only: these plants are not included in the primary market "
                "analysis unless they were also selected in Step 2."
            )
            if context_only:
                preview = context_only[:_MAX_MARKET_CHECK_PLANTS]
                st.write(", ".join(preview))
                if len(context_only) > len(preview):
                    st.caption(
                        f"+{len(context_only) - len(preview)} additional context plant(s)."
                    )
            else:
                st.write("All broader-context plants are already in the Step 2 shortlist.")

    if isinstance(landscape_df, pd.DataFrame) and not landscape_df.empty:
        compact_columns = [
            "Plant",
            "Region_of_Origin",
            "EMA_HMPC_Status",
            "WHO_Status",
            "ESCOP_Status",
            "US_Status",
            "UK_Status",
            "Patent_Search_Status",
            "Retail_Products_Status",
        ]
        compact_columns = [c for c in compact_columns if c in landscape_df.columns]
        st.caption(
            "Compact regulatory view. EMA/HMPC wording is summarized for readability; "
            "the source wording remains available below."
        )

        # Build the complete export before rendering the compact table.  This
        # places the explicit full-export button above the dataframe toolbar,
        # whose built-in CSV icon exports only the visible compact columns.
        preferred_export_columns = [
            "Plant",
            "Region_of_Origin",
            "EMA_HMPC_Status",
            "EMA_HMPC_Detail",
            "EMA_Source",
            "WHO_Status",
            "WHO_Source",
            "ESCOP_Status",
            "ESCOP_Source",
            "Regulatory_Source",
            "US_Status",
            "UK_Status",
            "Patent_Search_Status",
            "Patent_Detail",
            "Retail_Products_Status",
            "Retail_Products_Detail",
        ]
        export_columns = [
            column for column in preferred_export_columns
            if column in landscape_df.columns
        ]
        export_columns.extend(
            column for column in landscape_df.columns
            if column not in export_columns
        )
        market_export_df = landscape_df.loc[:, export_columns].copy()

        st.download_button(
            "⬇️ Download FULL market analysis (all columns)",
            data=market_export_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="step3_market_competitive_landscape_full.csv",
            mime="text/csv",
            key="rd_download_full_market_csv",
            help=(
                "Use this button for the complete export. The small download icon "
                "inside the table exports only the columns visible in the compact view."
            ),
            type="primary",
        )
        st.caption(
            "Use the red FULL export button above. The small download icon inside "
            "the table exports only the visible compact columns."
        )

        st.dataframe(landscape_df[compact_columns], width="stretch")

        detail_columns = [
            "Plant",
            "EMA_HMPC_Detail",
            "EMA_Source",
            "WHO_Status",
            "WHO_Source",
            "ESCOP_Status",
            "ESCOP_Source",
            "Regulatory_Source",
            "Patent_Detail",
            "Retail_Products_Detail",
        ]
        detail_columns = [c for c in detail_columns if c in landscape_df.columns]
        if detail_columns:
            with st.expander("Regulatory and market-source details", expanded=False):
                st.dataframe(landscape_df[detail_columns], width="stretch")



    st.markdown("---")
    st.markdown("## Step 4 — Existing Scientific Knowledge")

    st.caption(
        "Review the current scientific inventory for the Step 2 shortlist: "
        "plants, compounds, targets, mechanisms, evidence level, extraction, "
        "safety and source provenance. This is a knowledge map, not a claim of efficacy."
    )

    if st.button("Run Scientific Knowledge Analysis", type="primary", key="run_step2_science"):
        try:
            with st.spinner("Looking up known plants, compounds, mechanisms, safety and sources..."):
                offline_engine = _offline_engine()
                broad_inventory_df = offline_engine.known_inventory_df(indication)

            shortlist, shortlist_source = _get_step2_candidate_shortlist()
            if shortlist and isinstance(broad_inventory_df, pd.DataFrame):
                shortlist_keys = {str(x).strip().lower() for x in shortlist}
                primary_inventory_df = broad_inventory_df[
                    broad_inventory_df["Known_Plant"].fillna("").astype(str).str.strip().str.lower().isin(shortlist_keys)
                ].copy()
            else:
                primary_inventory_df = broad_inventory_df.copy()
                shortlist_source = "broader indication inventory fallback"

            st.session_state["rd_inventory_df"] = primary_inventory_df
            st.session_state["rd_inventory_df_broader"] = broad_inventory_df
            st.session_state["rd_science_input_source"] = shortlist_source

            if isinstance(primary_inventory_df, pd.DataFrame) and not primary_inventory_df.empty:
                st.success("✅ Scientific knowledge analysis completed.")
            else:
                st.warning(
                    "No scientific inventory rows were found for the selected Step 2 candidates. "
                    "The broader indication inventory is still available below for context."
                )

        except Exception as e:
            st.error(f"Scientific knowledge analysis failed: {e}")

    inventory_df = st.session_state.get("rd_inventory_df")
    broader_inventory_df = st.session_state.get("rd_inventory_df_broader")
    science_input_source = st.session_state.get("rd_science_input_source", "unavailable")

    if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty:
        n_known_plants = inventory_df["Known_Plant"].nunique() if "Known_Plant" in inventory_df.columns else 0
        n_known_compounds = inventory_df["Known_Compound"].nunique() if "Known_Compound" in inventory_df.columns else 0
        n_mechanisms = (
            inventory_df["Known_Mechanism"].replace("", pd.NA).dropna().nunique()
            if "Known_Mechanism" in inventory_df.columns else 0
        )
        n_sources = (
            inventory_df["Reference_URL"].replace("", pd.NA).dropna().nunique()
            if "Reference_URL" in inventory_df.columns else 0
        )

        st.caption(
            f"{n_known_plants} shortlisted plant(s), {n_known_compounds} known compound(s), "
            f"{n_mechanisms} mechanism statement(s), {n_sources} linked reference(s) "
            f"(source: {science_input_source})."
        )

        regulatory_df = st.session_state.get("rd_market_landscape_df")
        summary_df = _build_scientific_plant_summary(inventory_df, regulatory_df)

        st.markdown("### Plant-level scientific knowledge summary")
        st.dataframe(summary_df, width="stretch", hide_index=True)

        st.download_button(
            "⬇️ Download plant-level scientific summary (CSV)",
            data=summary_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="step4_scientific_knowledge_summary.csv",
            mime="text/csv",
            key="download_step4_summary_csv",
        )

        st.markdown("### Detailed plant–compound evidence inventory")
        st.caption(
            "Each row is one plant–compound record. Empty fields mean the source database "
            "does not currently contain that information; they are not filled by inference."
        )
        st.dataframe(inventory_df.head(500), width="stretch", hide_index=True)

        st.download_button(
            "⬇️ Download FULL scientific knowledge inventory (all columns)",
            data=inventory_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="step4_scientific_knowledge_full.csv",
            mime="text/csv",
            key="download_step4_full_csv",
        )

        if len(inventory_df) > 500:
            st.caption(
                f"Showing first 500 of {len(inventory_df)} detailed rows; "
                "the FULL CSV contains every row."
            )

    if isinstance(broader_inventory_df, pd.DataFrame) and not broader_inventory_df.empty:
        primary_plants = set(
            inventory_df["Known_Plant"].dropna().astype(str)
            if isinstance(inventory_df, pd.DataFrame) and "Known_Plant" in inventory_df.columns
            else []
        )
        broader_only = broader_inventory_df[
            ~broader_inventory_df["Known_Plant"].fillna("").astype(str).isin(primary_plants)
        ].copy()
        broader_count = broader_inventory_df["Known_Plant"].nunique()
        with st.expander(
            f"Broader scientific context — {broader_count} indication-linked plant(s)",
            expanded=False,
        ):
            st.caption(
                "Context only. These rows are not part of the primary Step 2 shortlist analysis."
            )
            st.dataframe(broader_only.head(300), width="stretch", hide_index=True)
            st.download_button(
                "Download broader scientific context (CSV)",
                data=broader_inventory_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="step4_broader_scientific_context.csv",
                mime="text/csv",
                key="download_step4_broader_csv",
            )

    st.markdown("---")
    st.markdown("## Step 5 — R&D Candidate Discovery & Decision Engine")

    st.caption(
        "Generate alternative botanical candidates and score them using evidence, "
        "mechanism plausibility, novelty, safety, regulatory feasibility, and market opportunity."
    )

    col1, col2 = st.columns(2)

    with col1:
        reference_plant = st.text_input(
            "Restrict to reference plant (optional)",
            value="",
            help="Leave empty to analyze every known plant for this indication.",
            key="rd_reference_plant",
        )

    with col2:
        reference_compound = st.text_input(
            "Restrict to reference compound (optional)",
            value="",
            key="rd_reference_compound",
        )

    use_live_search = st.checkbox(
        "Include live Europe PMC evidence search",
        value=False,
        help="Keep this off unless needed. It may hit rate limits.",
        key="rd_live_evidence_checkbox",
    )

    if st.button("Run Candidate Discovery", type="primary", key="run_step3_candidates"):
        try:
            engine = _build_engine(_get_evidence_df(), use_live_search=use_live_search)

            with st.spinner("Discovering and scoring R&D candidates..."):
                result_df = engine.run(
                    indication=indication,
                    dosage_form=dosage_form,
                    market=market,
                    reference_plant=reference_plant,
                    reference_compound=reference_compound,
                )

            st.session_state["rd_candidates_df"] = result_df

            if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                plant_summary_df, triage_audit_df = build_plant_candidate_shortlist(
                    result_df,
                    indication=indication,
                    dosage_form=dosage_form,
                    max_candidates=50,
                )
                st.session_state["rd_candidate_plant_summary_df"] = plant_summary_df
                st.session_state["rd_candidate_triage_audit_df"] = triage_audit_df

                counts = (
                    plant_summary_df["Scientific_Triage_Status"].value_counts()
                    if isinstance(plant_summary_df, pd.DataFrame) and not plant_summary_df.empty
                    else pd.Series(dtype=int)
                )
                shortlisted = int(counts.get("Shortlist", 0))
                exploratory = int(counts.get("Exploratory", 0))
                excluded = int(counts.get("Excluded", 0))
                st.success(
                    f"✅ {len(result_df)} raw plant–compound associations generated; "
                    f"aggregated into {shortlisted + exploratory + excluded} plant candidates "
                    f"({shortlisted} shortlisted, {exploratory} exploratory, {excluded} excluded)."
                )
            else:
                st.session_state.pop("rd_candidate_plant_summary_df", None)
                st.session_state.pop("rd_candidate_triage_audit_df", None)
                st.warning("No R&D candidates found.")

        except Exception as e:
            st.error(f"Candidate discovery failed: {e}")

    result_df = st.session_state.get("rd_candidates_df")

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        # Cheap (no network calls, pure string formatting over columns
        # already on the row) — applied automatically, unlike market
        # landscape enrichment which stays opt-in due to its real
        # network cost.
        result_df = add_development_concept_column(result_df, inputs.get("standardized_project"))

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        if "Reference_Plant" in result_df.columns:
            n_ref_plants = result_df["Reference_Plant"].nunique()
            if n_ref_plants <= 3:
                ref_names = ", ".join(
                    result_df["Reference_Plant"].dropna().unique()[:3]
                )
                st.warning(
                    f"⚠️ **Every candidate below traces back to just "
                    f"{n_ref_plants} reference plant(s)** ({ref_names}) — the "
                    f"only ones tagged with an indication matching this query "
                    "in the database. All rows are that plant's known "
                    "compounds fanned out across the whole database by "
                    "chemical similarity, not an independent scientific base "
                    "for this indication. Worth broadening the indication "
                    "tagging (Source Ingestion / Bulk Evidence Collection) "
                    "before treating this as a comprehensive result."
                )
        plant_summary_df = st.session_state.get("rd_candidate_plant_summary_df")
        triage_audit_df = st.session_state.get("rd_candidate_triage_audit_df")
        if not isinstance(plant_summary_df, pd.DataFrame) or plant_summary_df.empty:
            plant_summary_df, triage_audit_df = build_plant_candidate_shortlist(
                result_df,
                indication=indication,
                dosage_form=dosage_form,
                max_candidates=50,
            )
            st.session_state["rd_candidate_plant_summary_df"] = plant_summary_df
            st.session_state["rd_candidate_triage_audit_df"] = triage_audit_df

        st.info(
            "📊 **Scientific triage view:** the raw chemical-association network is "
            "kept for audit, but the primary table is one row per alternative plant. "
            "A plant enters `Shortlist` only when at least one row has traceable "
            "alternative-plant evidence, a supported target/mechanism, a "
            "non-generic chemical signal, no hard safety/regulatory stop, and no "
            "documented dosage-form mismatch. `Exploratory` means a plausible but "
            "incomplete hypothesis; `Excluded` means it failed a non-compensatory "
            "gate. `Scientific_Triage_Score` is transparent triage, not an efficacy claim."
        )

        if isinstance(plant_summary_df, pd.DataFrame) and not plant_summary_df.empty:
            primary_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"].isin(["Shortlist", "Exploratory"])
            ].copy()
            excluded_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"] == "Excluded"
            ].copy()

            st.markdown("### Plant-centric candidate shortlist")
            if primary_df.empty:
                st.warning(
                    "No plant passed the current scientific shortlisting gates. "
                    "Review the excluded-row audit rather than treating raw compound matches as candidates."
                )
            else:
                st.dataframe(primary_df.head(50), width="stretch", hide_index=True)

            st.download_button(
                "Download plant-centric scientific shortlist (CSV)",
                data=plant_summary_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="step5_plant_centric_scientific_shortlist.csv",
                mime="text/csv",
                key="rd_download_plant_shortlist_csv",
            )

            with st.expander(f"Excluded plant candidates — {len(excluded_df)}", expanded=False):
                st.caption(
                    "These plants remain visible for audit; the reason is shown in "
                    "Why_Selected_or_Rejected."
                )
                if not excluded_df.empty:
                    st.dataframe(excluded_df.head(200), width="stretch", hide_index=True)

        with st.expander(
            f"Raw plant–compound association network — {len(result_df)} row(s)",
            expanded=False,
        ):
            st.warning(
                "Exploratory network only. Each row is a chemical/evidence association, "
                "not an independently validated botanical candidate."
            )
            st.dataframe(result_df.head(500), width="stretch")
            if len(result_df) > 500:
                st.caption(f"Showing first 500 of {len(result_df)} raw rows in this preview.")
            st.download_button(
                "Download raw association network (CSV)",
                data=result_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="step5_raw_candidate_association_network.csv",
                mime="text/csv",
                key="rd_download_raw_candidate_network_csv",
            )

        if isinstance(triage_audit_df, pd.DataFrame) and not triage_audit_df.empty:
            with st.expander("Scientific gate audit — every raw row", expanded=False):
                st.caption(
                    "Shows exactly which generic gates each raw row passed or failed."
                )
                audit_cols = [c for c in [
                    "Reference_Plant", "Alternative_Plant",
                    "Shared_or_Similar_Compound", "Target_or_Mechanism",
                    "Scientific_Triage_Status", "Scientific_Triage_Reasons",
                    "Direct_Evidence_Present", "Supported_Target_or_Mechanism",
                    "Generic_Compound_Only", "Dosage_Form_Compatibility",
                    "Hard_Stop_Present", "Negative_Evidence_Present",
                    "Evidence_Level", "Evidence_Source", "Source_Record_IDs",
                ] if c in triage_audit_df.columns]
                st.dataframe(triage_audit_df[audit_cols].head(500), width="stretch")
                st.download_button(
                    "Download full scientific gate audit (CSV)",
                    data=triage_audit_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="step5_scientific_gate_audit.csv",
                    mime="text/csv",
                    key="rd_download_triage_audit_csv",
                )

        with st.expander("🌍 Enrich with market/patent landscape (optional, per-candidate)"):
            st.caption(
                "Merges each candidate's real regulatory (EMA/WHO/ESCOP), patent, "
                "and retail search status into the table above — kept separate "
                "from the default run because patent search makes a real network "
                "call when EPO_OPS_KEY/EPO_OPS_SECRET are configured. Retail "
                "search has no free data source and will honestly show "
                "\"Not configured\"/\"Not implemented\" until a paid search API "
                "is wired in (see _search_retail_products())."
            )
            unique_plant_count = result_df["Alternative_Plant"].nunique() if "Alternative_Plant" in result_df.columns else 0
            max_plants = st.slider(
                "Max unique plants to check", 5, 100, min(30, max(unique_plant_count, 5)),
                key="rd_market_landscape_max_plants",
                help=f"This result has {unique_plant_count} unique alternative plants.",
            )
            if st.button("Run market/patent landscape check", key="rd_enrich_market_btn"):
                with st.spinner("Checking regulatory/patent/retail status per plant..."):
                    enrich_engine = _build_engine(_get_evidence_df(), use_live_search=use_live_search)
                    enriched_df = enrich_engine.enrich_candidates_with_market_landscape(
                        result_df, max_plants=max_plants,
                    )
                st.session_state["rd_candidates_df_enriched"] = enriched_df

            enriched_df = st.session_state.get("rd_candidates_df_enriched")
            if isinstance(enriched_df, pd.DataFrame) and not enriched_df.empty:
                note = enriched_df["Market_Landscape_Note"].iloc[0] if "Market_Landscape_Note" in enriched_df.columns else ""
                if note:
                    st.warning(note)
                display_cols = [c for c in enriched_df.columns if c.startswith("Market_Landscape_") or c in ("Alternative_Plant", "Reference_Plant")]
                st.dataframe(enriched_df[display_cols].drop_duplicates(subset=["Alternative_Plant"]).head(200), width="stretch")
                st.download_button(
                    "Download enriched table (CSV)",
                    data=enriched_df.to_csv(index=False).encode("utf-8"),
                    file_name="botanical_rd_candidates_market_enriched.csv",
                    mime="text/csv",
                    key="rd_download_enriched_csv",
                )

        with st.expander("📐 Validate output contract (Data Contracts adapter)"):
            st.caption(
                "Checks every row against data_contracts.CandidateAssessment — "
                "the named schema this output is supposed to have. A clean "
                "result means the real columns and the documented contract "
                "still agree; any errors here mean something drifted (a "
                "renamed column, an unexpected type) and point to exactly "
                "which row and field."
            )
            if st.button("Run contract validation", key="rd_validate_contract_btn"):
                records, errors_df = validate_result_df(
                    result_df, indication=indication, project_id=f"{indication}-{market}",
                )
                if errors_df.empty:
                    st.success(
                        f"✅ All {len(records)} rows validated cleanly against "
                        f"the CandidateAssessment contract."
                    )
                else:
                    st.error(
                        f"⚠️ {len(errors_df)} contract issue(s) found across "
                        f"{errors_df['row_index'].nunique()} row(s) — "
                        f"{len(records)} of {len(result_df)} rows still "
                        f"validated cleanly."
                    )
                    st.dataframe(errors_df, width="stretch")

                # Task 4 — best-effort persistence of the just-validated
                # records as ONE locked, versioned decision record. A
                # decision record must represent a FULLY validated
                # analysis, never a partial one — so this only runs when
                # errors_df is empty (every row validated cleanly), not
                # merely when records is non-empty. Never blocks or
                # interrupts this page; only a minimal status message is
                # shown, per the same UI constraint already used for
                # Sprint 6A.2's telemetry persistence (no database/SQL
                # details exposed here). Append-only — see
                # decision_record_persistence.py's LOCK SEMANTICS.
                if errors_df.empty and records:
                    decision_record_summary = persist_decision_record(
                        records, indication=indication, project_id=f"{indication}-{market}",
                    )
                    if decision_record_summary["status"] == "persisted":
                        st.session_state["rd_last_decision_record_id"] = decision_record_summary["analysis_id"]
                        st.caption(
                            f"✅ Decision record persisted "
                            f"(analysis_id: {decision_record_summary['analysis_id']})"
                        )
                    else:
                        st.caption("ℹ️ Decision-record persistence unavailable")
                elif records:
                    st.caption(
                        "ℹ️ Decision record not persisted — contract validation "
                        "found issues, so this analysis is not yet complete."
                    )

        # Task 2 — Scoring sensitivity / ranking robustness. Purely
        # additive: prepare_sensitivity_payload() only calls the
        # existing fragility_report()/build_robustness_analysis()
        # entry points in scoring_sensitivity_report.py on the SAME
        # result_df already produced above — no re-run of engine.run(),
        # no new scoring logic, no change to result_df itself.
        with st.expander("Scoring sensitivity and ranking robustness", expanded=False):
            payload = prepare_sensitivity_payload(result_df)

            if payload["status"] == "insufficient_data":
                st.info(payload["message"])
            else:
                fragility = payload["fragility"]
                if fragility:
                    st.caption(fragility["summary"])

                counts = payload["rank_stability_counts"] or {}
                if counts:
                    ordered_levels = [
                        lvl for lvl in ("Stable", "Moderately stable", "Fragile", "Tied", "Insufficient")
                        if lvl in counts
                    ]
                    cols = st.columns(len(ordered_levels)) if ordered_levels else []
                    for col, level in zip(cols, ordered_levels):
                        col.metric(level, counts[level])

            st.divider()
            st.markdown(f"**{payload['boundary_statement']}**")
            st.caption(payload["boundary_explanation"])

        st.download_button(
            "Download decision table (CSV)",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name="botanical_rd_candidates.csv",
            mime="text/csv",
        )

        # Task 13.2C — per-item scientific evidence detail. Built ONCE
        # here, outside pharma_report_generator.py entirely: collect
        # this analysis's evidence_record_ids (already on every
        # candidate row via Task 10.2's Applicability_Summary), resolve
        # them against the same evidence_df already loaded for this
        # session, then convert to a presentation-safe payload before
        # it ever reaches the report layer. generate_pharma_report()
        # only ever receives the final plain-dict payload below — it
        # never imports standard_evidence_builder, never sees a
        # ScientificEvidence object, and never touches evidence_df or
        # the engine itself.
        scientific_evidence_by_id = get_scientific_evidence_by_ids(
            _collect_evidence_record_ids(result_df), _get_evidence_df()
        )
        scientific_evidence_payload = build_scientific_evidence_presentation_payload(
            scientific_evidence_by_id
        )

        report_markdown = generate_pharma_report(
            result_df, indication=indication, dosage_form=dosage_form, market=market,
            standardized_project=inputs.get("standardized_project"),
            decision_record_id=st.session_state.get("rd_last_decision_record_id"),
            scientific_evidence_payload=scientific_evidence_payload,
        )
        st.download_button(
            "Download R&D report (Markdown)",
            data=report_markdown.encode("utf-8"),
            file_name="botanical_rd_report.md",
            mime="text/markdown",
            help="A structured, per-candidate write-up (scientific/commercial/regulatory "
                 "rationale, evidence strengths & weaknesses, next-experiment suggestion, "
                 "sources) for the top-scoring candidates, plus a summary table for the rest.",
        )

        with st.expander("Preview R&D report"):
            st.markdown(report_markdown)

    st.markdown("---")
    st.markdown("## Step 6 — Final Recommendation")

    st.caption(
        "Generate a concise R&D recommendation based on the decision table produced in Step 5."
    )

    if st.button("Generate Final Recommendation", type="primary", key="run_step4_recommendation"):
        st.session_state["show_final_recommendation"] = True

    if st.session_state.get("show_final_recommendation"):
        _recommendation_block(result_df)
