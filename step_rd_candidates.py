import pandas as pd
import streamlit as st

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from pharma_report_generator import generate_pharma_report


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


def _get_evidence_df():
    evidence_df = st.session_state.get("evidence_df")
    if isinstance(evidence_df, pd.DataFrame):
        return evidence_df
    return None


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
    from supabase_data import load_plant_compounds_df
    try:
        return load_plant_compounds_df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def _cached_compound_profiles_df():
    from supabase_data import load_compound_profiles_df
    try:
        return load_compound_profiles_df()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def _cached_scientific_evidence_df():
    from supabase_data import load_scientific_evidence_df
    try:
        return load_scientific_evidence_df()
    except Exception:
        return pd.DataFrame()


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


@st.cache_resource(ttl=120, show_spinner=False)
def _cached_engine(use_live_search: bool, evidence_fingerprint, _evidence_df=None):
    return BotanicalRDCandidateEngine(
        evidence_df=_evidence_df,
        use_live_search=use_live_search,
        plant_compounds_df=_cached_plant_compounds_df(),
        compound_profiles_df=_cached_compound_profiles_df(),
        scientific_evidence_df=_cached_scientific_evidence_df(),
    )


def _build_engine(evidence_df, use_live_search):
    fingerprint = _evidence_fingerprint(evidence_df)
    return _cached_engine(use_live_search, fingerprint, _evidence_df=evidence_df)


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
            with st.spinner("Loading known plant inventory..."):
                offline_engine = _offline_engine()
                inventory_df = offline_engine.known_inventory_df(indication)

            known_plants = (
                _unique_nonempty(inventory_df.get("Known_Plant", []))
                if not inventory_df.empty
                else []
            )

            st.session_state["rd_inventory_df_internal"] = inventory_df
            st.session_state["rd_known_plants"] = known_plants
            st.session_state["rd_known_plants_total"] = len(known_plants)

            if not known_plants:
                st.session_state["rd_market_landscape_df"] = pd.DataFrame()
                st.warning(
                    f"No known plant inventory found for '{indication}'. "
                    "Add seed data before running market analysis."
                )
            else:
                # Cap how many plants actually get probed for market status.
                # known_plants (session state) still keeps the FULL list for
                # Step 4/5 to use — only this market-landscape loop is capped.
                capped_plants = known_plants[:_MAX_MARKET_CHECK_PLANTS]

                # Reuse the already-loaded cached tables; only the
                # use_live_search flag differs from the offline engine, so
                # there's no new network fetch here even though this is a
                # second engine instance.
                market_engine = _build_engine(
                    _get_evidence_df(), use_live_search=live_market
                )

                with st.spinner(
                    f"Checking market and competitive landscape for "
                    f"{len(capped_plants)} plant(s)..."
                ):
                    landscape_df = market_engine.market_landscape_df(capped_plants)

                st.session_state["rd_market_landscape_df"] = landscape_df
                st.success("✅ Market analysis completed.")

        except Exception as e:
            st.error(f"Market analysis failed: {e}")

    known_plants = st.session_state.get("rd_known_plants", [])
    known_plants_total = st.session_state.get("rd_known_plants_total", len(known_plants))
    landscape_df = st.session_state.get("rd_market_landscape_df")

    if known_plants:
        shown = known_plants[:_MAX_MARKET_CHECK_PLANTS]
        st.write(
            f"**Known plants used for market check** "
            f"(showing {len(shown)} of {known_plants_total} found):"
        )
        st.write(", ".join(shown))
        if known_plants_total > len(shown):
            st.caption(
                f"+{known_plants_total - len(shown)} more plant(s) known for this "
                "indication, not probed for market status to keep this step fast. "
                "They're still available in Step 4 and Step 5."
            )

    if isinstance(landscape_df, pd.DataFrame) and not landscape_df.empty:
        st.dataframe(landscape_df, width="stretch")

    st.markdown("---")
    st.markdown("## Step 4 — Existing Scientific Knowledge")

    st.caption(
        "Show current scientific knowledge: known plants, compounds, targets, mechanisms, "
        "evidence level, extraction information, safety notes, and regulatory notes."
    )

    if st.button("Run Scientific Knowledge Analysis", type="primary", key="run_step2_science"):
        try:
            with st.spinner("Looking up known plants, compounds, and targets..."):
                offline_engine = _offline_engine()
                inventory_df = offline_engine.known_inventory_df(indication)
            st.session_state["rd_inventory_df"] = inventory_df

            if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty:
                st.success("✅ Scientific knowledge analysis completed.")
            else:
                st.warning(
                    f"No scientific inventory found for '{indication}' in the seed database."
                )

        except Exception as e:
            st.error(f"Scientific knowledge analysis failed: {e}")

    inventory_df = st.session_state.get("rd_inventory_df")

    if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty:
        if "Known_Plant" in inventory_df.columns and "Known_Compound" in inventory_df.columns:
            n_known_plants = inventory_df["Known_Plant"].nunique()
            st.caption(
                f"{n_known_plants} known plant(s), "
                f"{inventory_df['Known_Compound'].nunique()} known compound(s) catalogued."
            )
            if n_known_plants <= 3:
                st.warning(
                    f"⚠️ **Narrow reference base:** only {n_known_plants} plant(s) in "
                    f"the database are tagged with an `indication` matching '{indication}'. "
                    "Step 5's alternative-candidate search fans out from these few "
                    "plants' known compounds to the whole database — so every "
                    "downstream candidate ultimately traces back to just this "
                    "handful of starting points, not a broad scientific base for "
                    "this indication. This isn't a scoring error; it reflects how "
                    "much indication-tagged data exists yet. Consider adding more "
                    "plants for this indication via Source Ingestion or Bulk "
                    "Evidence Collection before treating Step 6's results as "
                    "comprehensive."
                )
        st.dataframe(inventory_df.head(500), width="stretch")
        if len(inventory_df) > 500:
            st.caption(
                f"Showing first 500 of {len(inventory_df)} rows. "
                "Use the CSV download in Step 5 for the full result set."
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
                st.success(f"✅ {len(result_df)} candidate rows generated.")
            else:
                st.warning("No R&D candidates found.")

        except Exception as e:
            st.error(f"Candidate discovery failed: {e}")

    result_df = st.session_state.get("rd_candidates_df")

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
        st.info(
            "📊 **How to read this table:** `R&D_Opportunity_Score` ranks rows by "
            "how worth investigating they are — it is a triage/priority number, "
            "not a claim of scientific validity. A shared compound name (even a "
            "rare, specific one) only means two plants share a chemical hypothesis; "
            "it says nothing about concentration, bioavailability, or proven "
            "effect. The column that actually reflects confidence is "
            "`Decision_Class`, together with `Evidence_Level` — only rows backed "
            "by real clinical or regulatory evidence can reach \"Strong R&D "
            "candidate\". Treat every row as a lead to verify, not a conclusion."
        )
        st.dataframe(result_df.head(500), width="stretch")
        if len(result_df) > 500:
            st.caption(f"Showing first 500 of {len(result_df)} rows in this preview.")

        st.download_button(
            "Download decision table (CSV)",
            data=result_df.to_csv(index=False).encode("utf-8"),
            file_name="botanical_rd_candidates.csv",
            mime="text/csv",
        )

        report_markdown = generate_pharma_report(
            result_df, indication=indication, dosage_form=dosage_form, market=market,
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
