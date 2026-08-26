import time
import threading

import pandas as pd
import streamlit as st

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from market_intelligence_engine import MarketIntelligenceEngine
from pharma_report_generator import generate_pharma_report
from product_development_concept import add_development_concept_column
from candidate_output_adapter import validate_result_df
from candidate_shortlisting import build_plant_candidate_shortlist, merge_authoritative_scores
from sensitivity_display_adapter import prepare_sensitivity_payload
from decision_record_persistence import persist_decision_record
from decision_metadata import build_decision_metadata
from decision_explainability import attach_decision_explanations
from standard_evidence_builder import (
    build_scientific_evidence_presentation_payload,
    get_scientific_evidence_by_ids,
    build_transferability_target_context,
)


# TEMPORARY DIAGNOSTIC INSTRUMENTATION (performance audit — runtime hang
# in indication-centric Candidate Discovery). Prints only; no behavior
# change. See the "Run Candidate Discovery" button handler below.
def _perf(msg):
    print(f"[PERF] {msg}", flush=True)


# Step 5 performance guardrails.  Commercial evidence can contribute at most
# five points to the authoritative plant-level score, so candidates more than
# this margin below the current top-50 boundary cannot enter the final top 50
# solely because of market enrichment.  We still keep a generous hard cap for
# pathological tie-heavy datasets.
_STEP5_FINAL_MAX_CANDIDATES = 50
_STEP5_COMMERCIAL_SCORE_MARGIN = 5.0
_STEP5_COMMERCIAL_MAX_PLANTS = 120



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


def _attach_commercial_market_intelligence(
    result_df, *, evidence_df, indication, dosage_form, market, candidate_plants=None
):
    """Attach one indication-aware commercial snapshot per candidate plant.

    This is a local post-processing layer over the already-loaded structured
    market evidence.  It performs no network calls, does not alter scientific
    evidence, and never treats missing market data as white space.  The legacy
    ``Market_Status``/``Novelty_Status`` columns remain untouched for backward
    compatibility; new ``Commercial_*`` and ``Chemical_Differentiation_Status``
    columns make the two concepts explicit.
    """
    if not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return result_df

    out = result_df.copy()
    if "Chemical_Differentiation_Status" not in out.columns and "Novelty_Status" in out.columns:
        out["Chemical_Differentiation_Status"] = out["Novelty_Status"]

    if "Alternative_Plant" not in out.columns:
        return out

    engine = MarketIntelligenceEngine(evidence_df)

    # IMPORTANT PERFORMANCE RULE: Step 5 passes a bounded pre-shortlist here.
    # Never silently expand that back to every raw candidate plant.
    if candidate_plants is None:
        plants = [
            str(v).strip() for v in out["Alternative_Plant"].dropna().unique().tolist()
            if str(v).strip()
        ]
    else:
        allowed = {str(v).strip().lower() for v in candidate_plants if str(v).strip()}
        plants = [
            str(v).strip() for v in out["Alternative_Plant"].dropna().unique().tolist()
            if str(v).strip() and str(v).strip().lower() in allowed
        ]
    if not plants:
        return out

    # If there is no structured market evidence at all, do not call evaluate()
    # once per candidate just to rediscover the same SEARCH_NOT_PERFORMED state.
    # Populate the honest neutral fields in one vectorized assignment instead.
    if getattr(engine, "_market_rows", pd.DataFrame()).empty:
        indication_status = "UNKNOWN" if str(indication or "").strip() else "NOT_REQUESTED"
        defaults = {
            "Commercial_Market_Status": "Search not performed",
            "Commercial_Search_Status": "SEARCH_NOT_PERFORMED",
            "Commercial_Market_Data_Usable": False,
            "Commercial_Market_Score": None,
            "Commercial_Market_Saturation": "UNKNOWN",
            "Commercial_Status_Overall": "UNKNOWN",
            "Commercial_Status_For_Indication": indication_status,
            "Commercial_Novelty_Status": "Commercial novelty not assessed",
            "Commercial_Positioning": "Market data incomplete — do not classify as new commercial R&D",
            "Overall_Product_Hits": 0,
            "Indication_Product_Hits": 0,
            "Indication_Brand_Count": 0,
            "Indication_Market_Saturation": "UNKNOWN",
            "Indication_Market_Search_Status": "SEARCH_NOT_PERFORMED" if str(indication or "").strip() else "NOT_REQUESTED",
            "Indication_Market_Data_Usable": False,
            "Indication_Market_Score": None,
            "Indication_Matched_Terms": None,
            "Indication_Unclear_Product_Count": 0,
            "Indication_Explicit_Nonmatch_Product_Count": 0,
        }
        plant_mask = out["Alternative_Plant"].fillna("").astype(str).str.strip().str.lower().isin(
            {p.lower() for p in plants}
        )
        for column, value in defaults.items():
            if column not in out.columns:
                out[column] = None
            if isinstance(value, (list, dict, set)):
                out.loc[plant_mask, column] = [value] * int(plant_mask.sum())
            else:
                out.loc[plant_mask, column] = value
        return out

    rename = {
        "Market_Status": "Commercial_Market_Status",
        "Search_Status": "Commercial_Search_Status",
        "Market_Data_Usable": "Commercial_Market_Data_Usable",
        "Market_Score": "Commercial_Market_Score",
        "Market_Saturation": "Commercial_Market_Saturation",
        "Market_Evidence_Source_IDs": "Commercial_Market_Source_IDs",
        "Market_Retrieval_Timestamp": "Commercial_Market_Retrieval_Timestamp",
    }
    keep = {
        "Commercial_Market_Status", "Commercial_Search_Status",
        "Commercial_Market_Data_Usable", "Commercial_Market_Score",
        "Commercial_Market_Saturation", "Commercial_Market_Source_IDs",
        "Commercial_Market_Retrieval_Timestamp",
        "Commercial_Status_Overall", "Commercial_Status_For_Indication",
        "Commercial_Novelty_Status", "Commercial_Positioning",
        "Overall_Product_Hits", "Indication_Product_Hits",
        "Indication_Brand_Count", "Indication_Market_Saturation",
        "Indication_Market_Search_Status", "Indication_Market_Data_Usable",
        "Indication_Market_Score", "Indication_Matched_Terms",
        "Indication_Unclear_Product_Count",
        "Indication_Explicit_Nonmatch_Product_Count",
    }

    rows = []
    for plant in plants:
        snapshot = engine.evaluate(
            {"Scientific_Name": plant},
            indication=indication,
            dosage_form=dosage_form,
            market=market,
        )
        normalized = {rename.get(k, k): v for k, v in snapshot.items()}
        row = {"Alternative_Plant": plant}
        row.update({k: v for k, v in normalized.items() if k in keep})
        rows.append(row)

    market_df = pd.DataFrame(rows)
    if market_df.empty:
        return out

    # Drop only fields this function owns, allowing safe reuse on a DataFrame
    # that was already enriched during the same Streamlit session.
    owned = [c for c in market_df.columns if c != "Alternative_Plant" and c in out.columns]
    if owned:
        out = out.drop(columns=owned)
    return out.merge(market_df, on="Alternative_Plant", how="left")


def _step5_commercial_enrichment_plants(pre_summary_df):
    """Choose the only plants that need commercial enrichment in Step 5.

    The scientific/eligibility shortlist is built first.  Market opportunity
    can add at most five points, so only non-excluded plants within five points
    of the current final-top-50 boundary can plausibly enter that top 50 because
    of commercial evidence.  The hard cap protects tie-heavy datasets.
    """
    if not isinstance(pre_summary_df, pd.DataFrame) or pre_summary_df.empty:
        return []
    if "Alternative_Plant" not in pre_summary_df.columns:
        return []

    eligible = pre_summary_df.copy()
    if "Scientific_Triage_Status" in eligible.columns:
        eligible = eligible[eligible["Scientific_Triage_Status"] != "Excluded"]
    if eligible.empty:
        return []

    scores = pd.to_numeric(eligible.get("Overall_Score"), errors="coerce").fillna(0.0)
    eligible = eligible.assign(_step5_pre_score=scores).sort_values(
        "_step5_pre_score", ascending=False
    )
    if len(eligible) > _STEP5_FINAL_MAX_CANDIDATES:
        cutoff = float(eligible.iloc[_STEP5_FINAL_MAX_CANDIDATES - 1]["_step5_pre_score"])
        eligible = eligible[
            eligible["_step5_pre_score"] >= cutoff - _STEP5_COMMERCIAL_SCORE_MARGIN
        ]

    eligible = eligible.head(_STEP5_COMMERCIAL_MAX_PLANTS)
    return [
        str(v).strip() for v in eligible["Alternative_Plant"].tolist()
        if str(v).strip()
    ]


def _combine_step5_final_summary(pre_summary_df, enriched_summary_df):
    """Keep the re-scored enriched top candidates plus all excluded audit rows."""
    if not isinstance(enriched_summary_df, pd.DataFrame) or enriched_summary_df.empty:
        if not isinstance(pre_summary_df, pd.DataFrame):
            return pd.DataFrame()
        primary = pre_summary_df
        if "Scientific_Triage_Status" in primary.columns:
            keep = primary[primary["Scientific_Triage_Status"] != "Excluded"].head(
                _STEP5_FINAL_MAX_CANDIDATES
            )
            excluded = primary[primary["Scientific_Triage_Status"] == "Excluded"]
            return pd.concat([keep, excluded], ignore_index=True)
        return primary.head(_STEP5_FINAL_MAX_CANDIDATES).reset_index(drop=True)

    enriched_primary = enriched_summary_df
    if "Scientific_Triage_Status" in enriched_primary.columns:
        enriched_primary = enriched_primary[
            enriched_primary["Scientific_Triage_Status"] != "Excluded"
        ].head(_STEP5_FINAL_MAX_CANDIDATES)

    if isinstance(pre_summary_df, pd.DataFrame) and "Scientific_Triage_Status" in pre_summary_df.columns:
        excluded = pre_summary_df[pre_summary_df["Scientific_Triage_Status"] == "Excluded"]
    else:
        excluded = pd.DataFrame()
    return pd.concat([enriched_primary, excluded], ignore_index=True)



def _norm_run_context(value):
    return " ".join(str(value or "").strip().lower().split())


def _get_step2_retrieval_coverage(*, indication, market):
    """Return the run-scoped per-plant coverage map for these exact inputs.

    An explicit empty mapping means coverage is NOT ASSESSABLE for the current
    decision run.  Historical Supabase rows are never used to manufacture a
    completeness claim.
    """
    research_output = st.session_state.get("research_output")
    if not isinstance(research_output, dict):
        return {}
    if _norm_run_context(research_output.get("retrieval_coverage_market")) != _norm_run_context(market):
        return {}
    if _norm_run_context(research_output.get("retrieval_coverage_indication")) != _norm_run_context(indication):
        return {}
    coverage = research_output.get("retrieval_coverage_by_plant")
    return coverage if isinstance(coverage, dict) else {}


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

@st.cache_data(ttl=3600, show_spinner=False)
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


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_compound_profiles_df():
    """See _cached_plant_compounds_df's docstring — same (df, succeeded) contract."""
    from supabase_data import load_compound_profiles_df
    try:
        return load_compound_profiles_df(), True
    except Exception:
        return pd.DataFrame(), False


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_scientific_evidence_df():
    """See _cached_plant_compounds_df's docstring — same (df, succeeded) contract."""
    from supabase_data import load_scientific_evidence_df
    try:
        return load_scientific_evidence_df(), True
    except Exception:
        return pd.DataFrame(), False


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_evidence_records_df():
    """Full paginated evidence_records read, cached for one hour.

    The engine historically loaded this structured table independently of the
    canonical ``evidence_df`` supplied by app.py. We preserve that scientific
    data path, but stop downloading the same 20k+ rows on every engine build.
    """
    from supabase_data import load_evidence_records_df
    try:
        return load_evidence_records_df(), True
    except Exception:
        return pd.DataFrame(), False


_CANDIDATE_DISCOVERY_PROCESS_LOCK = threading.Lock()


def _candidate_discovery_process_lock():
    """One process-wide lock preventing Streamlit cache stampedes.

    Streamlit can execute multiple script threads when a user double-clicks,
    refreshes during a long run, or opens the same app in several tabs. Before
    this guard, those threads could all miss the same cold cache at once and
    each download/build the 20k+ row evidence universe independently.
    """
    return _CANDIDATE_DISCOVERY_PROCESS_LOCK


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
        # JSONB/list/dict cells are common in evidence_records and are not
        # always hashable by pandas directly. Falling back to row-count only
        # can keep a stale engine when a record is edited in place without a
        # row-count change, so use a deterministic string view before giving
        # up. This is cache invalidation only; the DataFrame itself is untouched.
        try:
            stable_view = evidence_df.astype(str)
            content_hash = int(pd.util.hash_pandas_object(stable_view, index=True).sum())
        except Exception:
            content_hash = hash((tuple(map(str, evidence_df.columns)), len(evidence_df)))
    return (len(evidence_df), content_hash)


ENGINE_CACHE_VERSION = "step5_runtime_egress_guard_v1"


@st.cache_resource(ttl=3600, show_spinner=False)
def _cached_engine(
    use_live_search: bool,
    evidence_fingerprint,
    engine_cache_version: str,
    _evidence_df=None,
):
    plant_compounds_df, plant_compounds_ok = _cached_plant_compounds_df()
    compound_profiles_df, compound_profiles_ok = _cached_compound_profiles_df()
    scientific_evidence_df, scientific_evidence_ok = _cached_scientific_evidence_df()
    evidence_records_df, evidence_records_ok = _cached_evidence_records_df()

    # Preserve the pre-fix scientific data path exactly: evidence_df remains the
    # canonical deduplicated read supplied by app.py, while evidence_records_df
    # remains the full structured table used by indication-centric discovery.
    # The optimization is transport-only: the latter is now fetched at most once
    # per cache TTL instead of once per engine construction / concurrent click.
    return BotanicalRDCandidateEngine(
        evidence_df=_evidence_df,
        use_live_search=use_live_search,
        plant_compounds_df=plant_compounds_df,
        compound_profiles_df=compound_profiles_df,
        scientific_evidence_df=scientific_evidence_df,
        evidence_records_df=evidence_records_df,
        # Review #17: if any core Supabase load actually FAILED (not
        # just legitimately returned few/no rows), the engine caps
        # every recommendation at "Investigate" — a Go call must never
        # be issued on data that may not have actually loaded.
        data_source_reliable=(
            plant_compounds_ok and compound_profiles_ok
            and scientific_evidence_ok and evidence_records_ok
        ),
    )


def _build_engine(evidence_df, use_live_search):
    fingerprint = _evidence_fingerprint(evidence_df)
    return _cached_engine(
        use_live_search,
        fingerprint,
        ENGINE_CACHE_VERSION,
        _evidence_df=evidence_df,
    )


def _candidate_discovery_run_key(
    *, indication, dosage_form, market, reference_plant, reference_compound,
    discovery_mode, use_live_search, evidence_df,
):
    """Stable per-session key for exact-input result reuse.

    Re-clicking Run with unchanged inputs should display the already completed
    result, not execute another multi-minute scientific pipeline.
    """
    return (
        str(indication or "").strip().casefold(),
        str(dosage_form or "").strip().casefold(),
        str(market or "").strip().casefold(),
        str(reference_plant or "").strip().casefold(),
        str(reference_compound or "").strip().casefold(),
        str(discovery_mode or "").strip().casefold(),
        bool(use_live_search),
        _evidence_fingerprint(evidence_df),
        ENGINE_CACHE_VERSION,
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


def _detect_discovery_mode(result_df) -> str:
    """Single source of truth for "which discovery mode produced this
    result_df" — used by both the success-branch and the fallback-rebuild
    branch below so decision_metadata.build_decision_metadata() and the
    UI's own indication-mode banner never disagree about which mode ran."""
    if not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return "unknown"
    is_indication_mode = (
        "Scoring_Config_Version" in result_df.columns
        and result_df["Scoring_Config_Version"].astype(str).str.startswith("2.").any()
    ) or (
        "Reference_Plant" in result_df.columns
        and result_df["Reference_Plant"].astype(str).eq("Indication-centric discovery").all()
    )
    return "indication" if is_indication_mode else "compound_substitution"




def _prepare_plant_triage_display(df):
    """Return a concise user-facing plant-level triage table.

    Phase 3 made ``Overall_Score`` / ``R&D_Opportunity_Score`` the
    authoritative plant-level score. ``Scientific_Triage_Score`` is retained
    in the downloadable audit CSV as a legacy diagnostic, but must not be
    presented as the primary score in the Streamlit table.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    view = df.copy()
    score_col = None
    for candidate in ("R&D_Opportunity_Score", "Overall_Score"):
        if candidate in view.columns:
            score_col = candidate
            break

    columns = ["Alternative_Plant"]
    if score_col:
        columns.append(score_col)
    columns.extend([
        "Evidence_Confidence",
        "Scientific_Triage_Status",
        "Go_Investigate_Hold_NoGo",
        "Commercial_Positioning",
        "Commercial_Novelty_Status",
        "Overall_Product_Hits",
        "Indication_Product_Hits",
        "Chemical_Differentiation_Status",
        "Indication_Relevance",
        "Evidence_Quality_Score",
        "Why_Selected_or_Rejected",
    ])
    columns = [column for column in columns if column in view.columns]
    view = view[columns].copy()

    if score_col:
        view[score_col] = pd.to_numeric(view[score_col], errors="coerce")
        view = view.sort_values(score_col, ascending=False, na_position="last")

    rename_map = {
        "Alternative_Plant": "Plant",
        "R&D_Opportunity_Score": "R&D Opportunity Score",
        "Overall_Score": "R&D Opportunity Score",
        "Evidence_Confidence": "Evidence Strength Index",
        "Scientific_Triage_Status": "Triage Status",
        "Go_Investigate_Hold_NoGo": "Decision",
        "Commercial_Positioning": "Commercial Positioning",
        "Commercial_Novelty_Status": "Commercial Novelty",
        "Overall_Product_Hits": "Overall Product Hits",
        "Indication_Product_Hits": "Indication Product Hits",
        "Chemical_Differentiation_Status": "Chemical Differentiation",
        "Indication_Relevance": "Indication Relevance",
        "Evidence_Quality_Score": "Evidence Quality Score",
        "Why_Selected_or_Rejected": "Why selected / rejected",
    }
    return view.rename(columns=rename_map).reset_index(drop=True)


def _eligible_mask(df: pd.DataFrame) -> pd.Series:
    """Phase 4 — Eligibility Gate. True only for rows explicitly marked
    ELIGIBLE / ELIGIBLE_WITH_RESTRICTIONS (Eligible_For_Normal_Ranking
    == True) — used as a final safety-net filter in BOTH the modern
    (report_ready_df) and legacy (result_df) branches of
    _recommendation_block(), so neither branch's own fallback logic can
    surface a hard no-go/incomplete/expert-review row, no matter how it
    got there. A row with neither column at all (pre-Phase-4 data) is
    treated as NOT eligible for normal ranking — see the Phase 4 design
    review: "رکورد قدیمی بدون eligibility data باید INCOMPLETE تلقی
    شود، نه ELIGIBLE."
    """
    if "Eligible_For_Normal_Ranking" in df.columns:
        return df["Eligible_For_Normal_Ranking"].fillna(False).astype(bool)
    if "Eligibility_Status" in df.columns:
        return df["Eligibility_Status"].astype(str).isin(
            ("eligible", "eligible_with_restrictions")
        )
    return pd.Series(False, index=df.index)


def _no_go_mask(df: pd.DataFrame) -> pd.Series:
    if "Eligibility_Status" in df.columns:
        return df["Eligibility_Status"].astype(str).isin(("no_go_safety", "no_go_regulatory"))
    return pd.Series(False, index=df.index)


def _recommendation_block(result_df, report_ready_df=None):
    # Phase 3 (IMPLEMENTATION_PLAN.md) — prefer the authoritative,
    # one-row-per-plant frame (merge_authoritative_scores()'s output) so
    # this block's picks can never disagree with the Step 5 shortlist or
    # the downloaded report about which plant is recommended. Falls back
    # to the pre-Phase-3 raw-row behavior only if no report-ready frame is
    # available yet (e.g. a session that ran Step 5 before this change).
    if isinstance(report_ready_df, pd.DataFrame) and not report_ready_df.empty:
        df = report_ready_df.copy()
        call_col = "Go_Investigate_Hold_NoGo" if "Go_Investigate_Hold_NoGo" in df.columns else None

        best_rows = df  # already one row per plant, already sorted by Overall_Score

        # Post-Phase-3-review fix (Issue 1): classify by normalized PREFIX,
        # not exact match. Exploratory candidates carry the value
        # "Investigate — verify before proceeding" (see
        # candidate_shortlisting._derive_go_call), which starts with
        # "Investigate" but is not equal to the bare string "Investigate" —
        # an exact-match .isin(["Go", "Investigate"]) silently dropped
        # every exploratory candidate from both sections entirely.
        recommended = best_rows
        weak = best_rows.iloc[0:0]
        if call_col:
            call_series = best_rows[call_col].fillna("").astype(str).str.strip()
            recommended = best_rows[
                call_series.str.startswith("Go") | call_series.str.startswith("Investigate")
            ]
            weak = best_rows[
                call_series.str.startswith("Hold") | call_series.str.startswith("No-Go")
            ]
            if recommended.empty:
                # Never fall back into rows already classified as weak —
                # an all-Hold/No-Go result set must not be relabeled
                # "recommended" just because nothing matched Go/Investigate.
                recommended = best_rows.drop(weak.index).head(5)

        # Phase 4 — Eligibility Gate safety net. Go_Investigate_Hold_
        # NoGo is already derived from Decision_Class_AH, which is now
        # itself eligibility-driven (see decision_class_ah.py), so this
        # should already be a no-op for correctly-labelled rows — kept
        # as an explicit, structural final filter (not relying solely
        # on string-prefix matching of call_col) so "recommended" can
        # never contain a row Eligible_For_Normal_Ranking says is not.
        recommended = recommended[_eligible_mask(recommended)]

        # Phase 7 — ranking score/order must never overrule the validated
        # scientific final-decision layer. When Final_Decision_Status is
        # present, only GO / GO WITH CAUTION may remain in the recommended
        # bucket. The score-based Go_Investigate_Hold_NoGo field is a ranking
        # prioritization call, not a substitute for scientific eligibility.
        if "Final_Decision_Status" in best_rows.columns:
            final_status = best_rows["Final_Decision_Status"].fillna("").astype(str).str.strip()
            # Apply the Phase 7 authority only where an authoritative final
            # status is actually present. Blank status means the structured
            # final-decision layer did not produce a decision for that row;
            # in that case keep the already validated Phase 3/4
            # Go/Investigate/Hold/No-Go classification instead of silently
            # demoting every blank-status candidate into the weak bucket.
            has_final_status = final_status.ne("")
            actionable_status = final_status.isin(("GO", "GO WITH CAUTION"))
            authoritative_non_go = has_final_status & ~actionable_status

            if authoritative_non_go.any():
                recommended = recommended.loc[
                    ~recommended.index.isin(best_rows.index[authoritative_non_go])
                ]
                scientific_non_go = best_rows.loc[authoritative_non_go]
                weak = pd.concat([weak, scientific_non_go]).loc[
                    lambda x: ~x.index.duplicated(keep="first")
                ]

        display_cols = [
            col for col in [
                "Alternative_Plant",
                "Target_or_Mechanism",
                "R&D_Opportunity_Score",
                "Final_Decision_Status",
                "Decision_Class_AH",
                "Go_Investigate_Hold_NoGo",
                "Safety_Flags",
                "Commercial_Positioning",
                "Commercial_Novelty_Status",
                "Overall_Product_Hits",
                "Indication_Product_Hits",
                "Commercial_Market_Status",
                "Commercial_Status_For_Indication",
                "Indication_Market_Search_Status",
                "Chemical_Differentiation_Status",
                "Rationale",
            ] if col in recommended.columns
        ]
        weak_display_cols = [
            col for col in display_cols + ["Why_Selected_or_Rejected"]
            if col in weak.columns
        ]

        st.markdown("### ✅ Recommended / worth validating")
        st.caption(
            "\"Recommended\" means worth a human researcher's time to validate. "
            "Scientific evidence, chemical/source differentiation, and commercial "
            "novelty are separate signals. A candidate is never labelled commercial "
            "white-space merely because market search was missing or because it has "
            "an alternative chemical source. `Final_Decision_Status` remains the "
            "scientific decision authority."
        )
        st.dataframe(recommended[display_cols].head(10), width="stretch")

        if not weak.empty:
            st.markdown("### 🔴 Weak / not recommended")
            st.caption(
                "Retained here (not deleted) so the rejection reason stays visible — "
                "see `Why_Selected_or_Rejected` / `Decision_Class_AH`."
            )
            st.dataframe(weak[weak_display_cols].head(10), width="stretch")
        return

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
            # Phase 4 fix: the pre-Phase-4 version of this fallback was
            # `best_rows.head(5)` — unfiltered by anything — which the
            # audit proved could surface a hard no-go candidate (a
            # regulatory-prohibited or safety-concern row) at the top of
            # "Recommended" whenever nothing matched the positive regex
            # above. Excluding no-go rows before taking the top 5 closes
            # that gap without requiring every candidate set to have a
            # "strong/promising" row.
            recommended = best_rows[~_no_go_mask(best_rows)].head(5)

    # Phase 4 — Eligibility Gate safety net (legacy branch). Same
    # reasoning as the modern branch above: an explicit, structural
    # final filter so eligibility is authoritative even if decision_col
    # text was somehow inconsistent with it.
    recommended = recommended[_eligible_mask(recommended)]

    display_cols = [
        col for col in [
            "Alternative_Plant",
            "Shared_or_Similar_Compound",
            "Target_or_Mechanism",
            "R&D_Opportunity_Score",
            "Decision_Class",
            "Safety_Flags",
            "Commercial_Positioning",
            "Commercial_Novelty_Status",
            "Overall_Product_Hits",
            "Indication_Product_Hits",
            "Commercial_Market_Status",
            "Commercial_Status_For_Indication",
            "Indication_Market_Search_Status",
            "Chemical_Differentiation_Status",
            "Rationale",
        ] if col in recommended.columns
    ]

    st.markdown("### ✅ Recommended / worth validating")
    st.caption(
        "\"Recommended\" means worth validation, not proof of efficacy or novelty. "
        "Chemical/source differentiation is shown separately from commercial status; "
        "missing commercial evidence does not count as market white-space."
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
    transferability_target_context = build_transferability_target_context(
        indication=indication,
        dosage_form=dosage_form,
        standardized_project=inputs.get("standardized_project"),
    )

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

                    # General commercial classification for the CURRENT indication.
                    # Keep it independent from the legacy regulatory/patent landscape:
                    # a plant can be commercially established overall but still be a
                    # repurposing candidate for this indication, or its indication
                    # positioning can simply be unverified.
                    commercial_df = _attach_commercial_market_intelligence(
                        pd.DataFrame({"Alternative_Plant": market_plants}),
                        evidence_df=_get_evidence_df(),
                        indication=indication,
                        dosage_form=dosage_form,
                        market=market,
                    )
                    if isinstance(commercial_df, pd.DataFrame) and not commercial_df.empty:
                        commercial_df = commercial_df.rename(columns={"Alternative_Plant": "Plant"})
                        commercial_cols = [
                            c for c in commercial_df.columns
                            if c == "Plant" or c.startswith("Commercial_")
                            or c.startswith("Indication_")
                            or c == "Overall_Product_Hits"
                        ]
                        landscape_df = landscape_df.merge(
                            commercial_df[commercial_cols].drop_duplicates(subset=["Plant"]),
                            on="Plant", how="left",
                        )

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
            "Commercial_Status_Overall",
            "Commercial_Status_For_Indication",
            "Commercial_Novelty_Status",
            "Overall_Product_Hits",
            "Indication_Product_Hits",
            "Indication_Market_Search_Status",
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
            "Commercial_Status_Overall",
            "Commercial_Status_For_Indication",
            "Commercial_Novelty_Status",
            "Commercial_Positioning",
            "Overall_Product_Hits",
            "Indication_Product_Hits",
            "Commercial_Market_Saturation",
            "Indication_Market_Saturation",
            "Indication_Market_Search_Status",
            "Commercial_Market_Source_IDs",
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
        "mechanism plausibility, chemical differentiation, safety, regulatory feasibility, "
        "and independently verified market opportunity. Missing market data never counts as novelty."
    )

    col1, col2 = st.columns(2)

    discovery_mode_label = st.radio(
        "Discovery objective",
        options=[
            "Find botanicals for an indication",
            "Find alternative botanical sources of an active compound",
        ],
        index=0,
        help=(
            "Indication mode ranks plants from plant–indication evidence. "
            "Compound-source mode retains the legacy chemical-substitution workflow."
        ),
        key="rd_discovery_mode",
    )
    discovery_mode = (
        "indication" if discovery_mode_label.startswith("Find botanicals")
        else "compound_substitution"
    )

    with col1:
        reference_plant = st.text_input(
            "Reference plant (compound-source mode only)",
            value="",
            help="Leave empty to analyze every known plant for this indication.",
            key="rd_reference_plant",
        )

    with col2:
        reference_compound = st.text_input(
            "Reference compound (compound-source mode only)",
            value="",
            key="rd_reference_compound",
        )

    use_live_search = st.checkbox(
        "Include live Europe PMC evidence search",
        value=False,
        help="Keep this off unless needed. It may hit rate limits.",
        key="rd_live_evidence_checkbox",
    )

    evidence_df_for_run = _get_evidence_df()
    run_key = _candidate_discovery_run_key(
        indication=indication,
        dosage_form=dosage_form,
        market=market,
        reference_plant=reference_plant,
        reference_compound=reference_compound,
        discovery_mode=discovery_mode,
        use_live_search=use_live_search,
        evidence_df=evidence_df_for_run,
    )

    discovery_lock = _candidate_discovery_process_lock()
    discovery_busy = discovery_lock.locked()
    run_clicked = st.button(
        "Run Candidate Discovery",
        type="primary",
        key="run_step3_candidates",
        disabled=discovery_busy,
    )
    if discovery_busy:
        st.caption(
            "Candidate Discovery is already running in this app process. "
            "A second copy will not be started; wait for the active run to finish."
        )

    _rerun_after_discovery = False
    if run_clicked:
        existing_result = st.session_state.get("rd_candidates_df")
        if (
            st.session_state.get("rd_candidate_run_key") == run_key
            and isinstance(existing_result, pd.DataFrame)
            and not existing_result.empty
        ):
            st.info("Same inputs detected — reusing the completed Step 5 result.")
            _rerun_after_discovery = True
        elif not discovery_lock.acquire(blocking=False):
            st.warning(
                "Another Candidate Discovery run started just before this click. "
                "No duplicate job was launched."
            )
        else:
            progress = st.progress(0.0, text="Preparing cached scientific data…")

            def _step5_progress(stage, current=0, total=0, message=""):
                # The indication engine reports real plant-level progress. The
                # stage offsets leave room for evidence-index construction and
                # plant-level shortlisting before/after the main scoring loop.
                if stage == "candidate_universe":
                    value = 0.05
                elif stage == "evidence_index":
                    value = 0.12
                elif stage == "profile":
                    value = 0.18
                elif stage == "embedding":
                    value = 0.22
                elif stage == "scoring":
                    fraction = (float(current) / float(total)) if total else 0.0
                    value = 0.22 + 0.63 * max(0.0, min(1.0, fraction))
                elif stage == "discovery_done":
                    value = 0.86
                else:
                    value = 0.02
                progress.progress(
                    max(0.0, min(1.0, value)),
                    text=message or "Discovering and scoring R&D candidates…",
                )

            try:
                _perf_t0 = time.perf_counter()
                _perf(f"build_engine start discovery_mode={discovery_mode!r} indication={indication!r}")
                engine = _build_engine(
                    evidence_df_for_run,
                    use_live_search=use_live_search,
                )
                _perf(f"build_engine done elapsed={time.perf_counter() - _perf_t0:.3f}")

                with st.spinner("Discovering and scoring R&D candidates..."):
                    _perf_t_run = time.perf_counter()
                    result_df = engine.run(
                        indication=indication,
                        dosage_form=dosage_form,
                        market=market,
                        reference_plant=reference_plant,
                        reference_compound=reference_compound,
                        discovery_mode=discovery_mode,
                        progress_callback=_step5_progress,
                        target_context=transferability_target_context,
                        retrieval_coverage_by_plant=_get_step2_retrieval_coverage(
                            indication=indication, market=market
                        ),
                    )
                    _perf(
                        f"engine.run() done rows={0 if result_df is None else len(result_df)} "
                        f"elapsed={time.perf_counter() - _perf_t_run:.3f} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )

                # Build the scientific/eligibility shortlist FIRST.  The previous
                # implementation enriched every unique raw candidate before this
                # reduction, which made Step 5 scale with the entire candidate
                # universe instead of the decision set.
                if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                    progress.progress(0.87, text="Building scientific pre-shortlist…")
                    _perf_t_pre_shortlist = time.perf_counter()
                    pre_summary_df, triage_audit_df = build_plant_candidate_shortlist(
                        result_df,
                        indication=indication,
                        dosage_form=dosage_form,
                        max_candidates=0,
                        target_context=transferability_target_context,
                    )
                    market_plants = _step5_commercial_enrichment_plants(pre_summary_df)
                    _perf(
                        f"pre-shortlist done plants={len(pre_summary_df)} "
                        f"market_enrichment_plants={len(market_plants)} "
                        f"elapsed={time.perf_counter() - _perf_t_pre_shortlist:.3f}"
                    )

                    progress.progress(0.90, text="Checking commercial status for shortlisted candidates…")
                    _perf_t_market = time.perf_counter()
                    result_df = _attach_commercial_market_intelligence(
                        result_df,
                        evidence_df=evidence_df_for_run,
                        indication=indication,
                        dosage_form=dosage_form,
                        market=market,
                        candidate_plants=market_plants,
                    )
                    _perf(
                        f"commercial enrichment done plants={len(market_plants)} "
                        f"elapsed={time.perf_counter() - _perf_t_market:.3f}"
                    )

                    # Re-score only the bounded enriched pool.  Scientific triage
                    # for the whole raw universe was already computed above; doing
                    # a second full-universe aggregation would throw away the
                    # performance gain.
                    if market_plants:
                        market_keys = {p.lower() for p in market_plants}
                        selected_raw = result_df[
                            result_df["Alternative_Plant"].fillna("").astype(str).str.strip().str.lower().isin(market_keys)
                        ]
                        enriched_summary_df, _ = build_plant_candidate_shortlist(
                            selected_raw,
                            indication=indication,
                            dosage_form=dosage_form,
                            max_candidates=_STEP5_FINAL_MAX_CANDIDATES,
                            target_context=transferability_target_context,
                        )
                    else:
                        enriched_summary_df = pd.DataFrame()
                    plant_summary_df = _combine_step5_final_summary(
                        pre_summary_df, enriched_summary_df
                    )
                else:
                    plant_summary_df, triage_audit_df = pd.DataFrame(), pd.DataFrame()

                st.session_state["rd_candidates_df"] = result_df
                # Any previously prepared CSV bytes belong to the former run.
                st.session_state.pop("rd_raw_candidate_csv_bytes", None)
                st.session_state.pop("rd_triage_audit_csv_bytes", None)

                if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                    _perf(
                        f"final plant shortlist ready plants={0 if plant_summary_df is None else len(plant_summary_df)} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )
                    st.session_state["rd_candidate_plant_summary_df"] = plant_summary_df
                    st.session_state["rd_candidate_triage_audit_df"] = triage_audit_df
                    # Phase 3 (IMPLEMENTATION_PLAN.md) — the single authoritative,
                    # report-ready frame. Both the recommendation block and the
                    # downloaded report are built from THIS, not from result_df
                    # directly, so they can never disagree with the shortlist
                    # above about which plant is the top candidate.
                    _perf_t_merge = time.perf_counter()
                    st.session_state["rd_report_ready_df"] = merge_authoritative_scores(
                        result_df, plant_summary_df
                    )
                    _perf(
                        f"merge_authoritative_scores() done "
                        f"elapsed={time.perf_counter() - _perf_t_merge:.3f} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )
                    # Phase 4 (IMPLEMENTATION_PLAN.md) — computed ONCE per
                    # decision run, from the same report_ready_df just built.
                    # Both the downloaded report and the persisted decision
                    # record read this exact dict — see build_decision_metadata()'s
                    # own docstring.
                    _perf_t_decision = time.perf_counter()
                    st.session_state["rd_decision_metadata"] = build_decision_metadata(
                        st.session_state["rd_report_ready_df"],
                        indication=indication, dosage_form=dosage_form, market=market,
                        discovery_mode=_detect_discovery_mode(result_df),
                    )
                    _perf(
                        f"build_decision_metadata() done "
                        f"elapsed={time.perf_counter() - _perf_t_decision:.3f} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )
                    # PHASE 6 — additive structured causal trace.  This reads the
                    # authoritative score/gate outputs and triage audit only; it never
                    # changes scoring, gating, ranking, connectors, or UI behaviour.
                    st.session_state["rd_report_ready_df"] = attach_decision_explanations(
                        st.session_state["rd_report_ready_df"],
                        triage_audit_df,
                        decision_metadata=st.session_state["rd_decision_metadata"],
                    )

                    counts = (
                        plant_summary_df["Scientific_Triage_Status"].value_counts()
                        if isinstance(plant_summary_df, pd.DataFrame) and not plant_summary_df.empty
                        else pd.Series(dtype=int)
                    )
                    shortlisted = int(counts.get("Shortlist", 0))
                    exploratory = int(counts.get("Exploratory", 0))
                    excluded = int(counts.get("Excluded", 0))
                    st.session_state["rd_candidate_run_key"] = run_key
                    progress.progress(1.0, text="Candidate Discovery complete.")
                    st.success(
                        f"✅ {len(result_df)} raw plant–compound associations generated; "
                        f"aggregated into {shortlisted + exploratory + excluded} plant candidates "
                        f"({shortlisted} shortlisted, {exploratory} exploratory, {excluded} excluded)."
                    )
                    # Render the result in a fresh, lightweight rerun only AFTER
                    # releasing the process lock in the finally block below.
                    _rerun_after_discovery = True
                else:
                    st.session_state.pop("rd_candidate_plant_summary_df", None)
                    st.session_state.pop("rd_candidate_triage_audit_df", None)
                    st.session_state.pop("rd_candidate_run_key", None)
                    progress.progress(1.0, text="Candidate Discovery finished — no candidates found.")
                    st.warning("No R&D candidates found.")

            except Exception as e:
                st.session_state.pop("rd_candidate_run_key", None)
                st.error(f"Candidate discovery failed: {e}")
            finally:
                discovery_lock.release()

    if _rerun_after_discovery:
        _perf("Step 5 result ready; rerunning UI after releasing discovery lock")
        st.rerun()

    result_df = st.session_state.get("rd_candidates_df")

    # Do not enrich all raw rows automatically. At several thousand rows,
    # row-wise development-concept formatting is not cheap on Streamlit Cloud
    # and was the main reason the page kept showing "Stop" after discovery had
    # already completed. It is prepared lazily only when the user requests the
    # full raw audit export below.

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        is_indication_mode = _detect_discovery_mode(result_df) == "indication"
        if is_indication_mode:
            st.info(
                "🔎 **Indication-centric discovery:** candidates enter through "
                "plant-specific indication or mechanism evidence. Shared chemistry "
                "is supporting metadata only and is not used as an entry gate."
            )
        elif "Reference_Plant" in result_df.columns:
            n_ref_plants = result_df["Reference_Plant"].nunique()
            if n_ref_plants <= 3:
                ref_names = ", ".join(result_df["Reference_Plant"].dropna().unique()[:3])
                st.warning(
                    f"⚠️ **Every candidate below traces back to just {n_ref_plants} "
                    f"reference plant(s)** ({ref_names}). Broaden the reference base "
                    "before treating compound-source results as comprehensive."
                )
        plant_summary_df = st.session_state.get("rd_candidate_plant_summary_df")
        triage_audit_df = st.session_state.get("rd_candidate_triage_audit_df")
        if not isinstance(plant_summary_df, pd.DataFrame) or plant_summary_df.empty:
            _perf_t0_fallback = time.perf_counter()
            _perf("fallback-path build_plant_candidate_shortlist() start (session_state was empty)")
            plant_summary_df, triage_audit_df = build_plant_candidate_shortlist(
                result_df,
                indication=indication,
                dosage_form=dosage_form,
                max_candidates=50,
                target_context=transferability_target_context,
            )
            _perf(f"fallback-path build_plant_candidate_shortlist() done elapsed={time.perf_counter() - _perf_t0_fallback:.3f}")
            st.session_state["rd_candidate_plant_summary_df"] = plant_summary_df
            st.session_state["rd_candidate_triage_audit_df"] = triage_audit_df
            _perf_t_merge_fallback = time.perf_counter()
            st.session_state["rd_report_ready_df"] = merge_authoritative_scores(
                result_df, plant_summary_df
            )
            _perf(f"fallback-path merge_authoritative_scores() done elapsed={time.perf_counter() - _perf_t_merge_fallback:.3f}")
            _perf_t_decision_fallback = time.perf_counter()
            st.session_state["rd_decision_metadata"] = build_decision_metadata(
                st.session_state["rd_report_ready_df"],
                indication=indication, dosage_form=dosage_form, market=market,
                discovery_mode=_detect_discovery_mode(result_df),
            )
            _perf(f"fallback-path build_decision_metadata() done elapsed={time.perf_counter() - _perf_t_decision_fallback:.3f}")
        report_ready_df = st.session_state.get("rd_report_ready_df")
        if not isinstance(report_ready_df, pd.DataFrame):
            report_ready_df = merge_authoritative_scores(result_df, plant_summary_df)
            st.session_state["rd_report_ready_df"] = report_ready_df
        decision_metadata = st.session_state.get("rd_decision_metadata")
        if not decision_metadata:
            decision_metadata = build_decision_metadata(
                report_ready_df, indication=indication, dosage_form=dosage_form,
                market=market, discovery_mode=_detect_discovery_mode(result_df),
            )
            st.session_state["rd_decision_metadata"] = decision_metadata

        st.info(
            "📊 **Scientific triage:** the main view shows only plant-level results. "
            "Raw plant–compound associations and excluded rows remain available as CSV audit files. "
            "The triage score prioritizes review; it is not an efficacy claim."
        )

        if isinstance(plant_summary_df, pd.DataFrame) and not plant_summary_df.empty:
            shortlist_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"] == "Shortlist"
            ].copy()
            exploratory_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"] == "Exploratory"
            ].copy()
            excluded_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"] == "Excluded"
            ].copy()

            st.markdown(f"### Scientific shortlist — {len(shortlist_df)} plant(s)")
            if shortlist_df.empty:
                st.warning(
                    "No plant passed all scientific gates. Raw chemical matches are not shown as candidates."
                )
            else:
                shortlist_display_df = _prepare_plant_triage_display(shortlist_df)
                st.dataframe(
                    shortlist_display_df,
                    width="stretch",
                    hide_index=True,
                    height=min(420, 86 + 44 * len(shortlist_display_df)),
                )

            with st.expander(
                f"Exploratory candidates — showing top {min(20, len(exploratory_df))} of {len(exploratory_df)}",
                expanded=False,
            ):
                st.caption(
                    "Plausible hypotheses with incomplete evidence. The complete list is included in the CSV export."
                )
                if not exploratory_df.empty:
                    exploratory_display_df = _prepare_plant_triage_display(
                        exploratory_df.head(20)
                    )
                    st.dataframe(
                        exploratory_display_df,
                        width="stretch",
                        hide_index=True,
                        height=min(520, 86 + 44 * len(exploratory_display_df)),
                    )

            st.download_button(
                "⬇️ Download complete plant-level triage (CSV)",
                data=plant_summary_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="step5_plant_centric_scientific_shortlist.csv",
                mime="text/csv",
                key="rd_download_plant_shortlist_csv",
                type="primary",
                help="Contains all shortlisted, exploratory and excluded plant candidates with reasons.",
            )

            st.caption(
                f"{len(excluded_df)} excluded plant(s) are not rendered on screen to keep the mobile page responsive; "
                "their gate failures and rejection reasons are preserved in the complete CSV."
            )

        st.markdown("#### Audit downloads")
        st.caption(
            "Large audit files are prepared only on request, so normal Step 5 viewing stays responsive on mobile."
        )

        raw_csv_bytes = st.session_state.get("rd_raw_candidate_csv_bytes")
        audit_csv_bytes = st.session_state.get("rd_triage_audit_csv_bytes")

        if raw_csv_bytes is None or (
            isinstance(triage_audit_df, pd.DataFrame)
            and not triage_audit_df.empty
            and audit_csv_bytes is None
        ):
            if st.button(
                "Prepare full audit CSV files",
                key="rd_prepare_audit_csv_btn",
                help="Formats the large raw network only when you actually need to download it.",
            ):
                with st.spinner("Preparing large audit files..."):
                    export_df = add_development_concept_column(
                        result_df, inputs.get("standardized_project")
                    )
                    st.session_state["rd_raw_candidate_csv_bytes"] = (
                        export_df.to_csv(index=False).encode("utf-8-sig")
                    )
                    if isinstance(triage_audit_df, pd.DataFrame) and not triage_audit_df.empty:
                        st.session_state["rd_triage_audit_csv_bytes"] = (
                            triage_audit_df.to_csv(index=False).encode("utf-8-sig")
                        )
                st.rerun()
        else:
            st.download_button(
                "Download raw plant–compound network (CSV)",
                data=raw_csv_bytes,
                file_name="step5_raw_candidate_association_network.csv",
                mime="text/csv",
                key="rd_download_raw_candidate_network_csv",
            )
            if audit_csv_bytes is not None:
                st.download_button(
                    "Download full scientific gate audit (CSV)",
                    data=audit_csv_bytes,
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
                        decision_metadata=st.session_state.get("rd_decision_metadata"),
                        # PHASE 2 (review round, issue 2) — the same
                        # evidence_df already loaded for this page,
                        # passed through so persist_decision_record()'s
                        # score_contributions can compute article-level
                        # evidence identity (not just raw database ids)
                        # for duplicate-score-contribution detection.
                        evidence_df=_get_evidence_df(),
                        # PHASE 6 — authoritative plant-level causal traces are
                        # persisted verbatim with the existing decision snapshot.
                        decision_explanations={
                            str(r.get("Alternative_Plant", "")): r.get("Decision_Explanation")
                            for _, r in st.session_state.get("rd_report_ready_df", pd.DataFrame()).iterrows()
                            if r.get("Decision_Explanation") is not None
                        },
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
                    st.caption("Leave-one-section-out rank stability")
                    ordered_levels = [
                        lvl for lvl in ("Stable", "Moderately stable", "Fragile", "Tied", "Insufficient")
                        if lvl in counts
                    ]
                    cols = st.columns(len(ordered_levels)) if ordered_levels else []
                    for col, level in zip(cols, ordered_levels):
                        col.metric(level, counts[level])

                perturb_counts = payload.get("weight_perturbation_stability_counts") or {}
                if perturb_counts:
                    st.caption("Actual ±10% section-weight perturbation")
                    ordered = [
                        lvl for lvl in ("Robust", "Moderately robust", "Sensitive")
                        if lvl in perturb_counts
                    ]
                    cols = st.columns(len(ordered)) if ordered else []
                    for col, level in zip(cols, ordered):
                        col.metric(level, perturb_counts[level])

                st.caption(
                    f"Ranking calibration status: {payload.get('ranking_calibration_status', 'unknown')} — "
                    f"{payload.get('ranking_calibration_notice', '')}"
                )

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

        report_ready_df = st.session_state.get("rd_report_ready_df")
        report_source_df = (
            report_ready_df
            if isinstance(report_ready_df, pd.DataFrame) and not report_ready_df.empty
            else result_df
        )
        report_markdown = generate_pharma_report(
            report_source_df, indication=indication, dosage_form=dosage_form, market=market,
            standardized_project=inputs.get("standardized_project"),
            decision_record_id=st.session_state.get("rd_last_decision_record_id"),
            scientific_evidence_payload=scientific_evidence_payload,
            decision_metadata=st.session_state.get("rd_decision_metadata"),
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
        _recommendation_block(result_df, st.session_state.get("rd_report_ready_df"))
