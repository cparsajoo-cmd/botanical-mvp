"""Stage 5 candidate-funnel architecture tests.

Proves the performance-fix architecture described in
STAGE5_CANDIDATE_FUNNEL_ROOT_CAUSE_REPORT.md:

  Supabase catalogue + Stage 2 novel candidates
      -> cheap high-recall pre-screen (stage5_candidate_prescreen.py)
      -> bounded expensive candidate pool
      -> ONE authoritative build_plant_candidate_shortlist() pass
      -> commercial enrichment
      -> rescore_commercial_component() (novelty/market only, in place)
      -> _finalize_step5_summary()

These tests exercise the composable pieces directly (the same pattern
already used by test_step5_market_intelligence_performance.py for
_attach_commercial_market_intelligence), since the full click-to-CSV flow
lives inside a Streamlit UI function (render_rd_candidates_step) that is not
independently unit-testable without a Streamlit runtime.
"""
import pandas as pd
import pytest

import candidate_shortlisting as cs
from candidate_shortlisting import (
    build_plant_candidate_shortlist,
    rescore_commercial_component,
)
from stage5_candidate_prescreen import (
    prescreen_candidate_universe,
    PRESCREEN_STATUS_SENT,
    PRESCREEN_STATUS_EXCLUDED,
)
from stage5_funnel_config import resolve_exploratory_budget
from step_rd_candidates import _finalize_step5_summary, _step5_commercial_enrichment_plants


def _direct_row(plant, **overrides):
    row = {
        "Alternative_Plant": plant,
        "Reference_Plant": "Reference plant",
        "Shared_or_Similar_Compound": "specific alkaloid",
        "Novelty_Status": "Rare / differentiating",
        "Target_or_Mechanism": "AMPK",
        "Target_Provenance": "Supported by source record",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human clinical evidence",
        "Candidate_Evidence_Strength_Tier": "Direct evidence",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": "PMID:123",
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "Regulatory_Barriers": "None identified",
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "Investigate",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "R&D_Opportunity_Score": 70,
    }
    row.update(overrides)
    return row


def _noise_row(plant, **overrides):
    row = {
        "Alternative_Plant": plant,
        "Reference_Plant": "Reference plant",
        "Shared_or_Similar_Compound": "",
        "Novelty_Status": "",
        "Target_or_Mechanism": "",
        "Target_Provenance": "not applicable",
        "Evidence_Level": "",
        "Evidence_Hierarchy_Detail": "",
        "Candidate_Evidence_Strength_Tier": "",
        "Evidence_Source": "",
        "Source_Record_IDs": "",
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "",
        "Interaction_Flags": "",
        "Regulatory_Barriers": "",
        "Decision_Class": "",
        "Decision_Class_AH": "",
        "Go_Investigate_Hold_NoGo": "",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "R&D_Opportunity_Score": 0,
    }
    row.update(overrides)
    return row


def _mechanistic_row(plant, **overrides):
    row = _noise_row(plant)
    row.update({
        "Target_or_Mechanism": "5-HT1A",
        "Target_Provenance": "Weak mechanistic overlap",
        "Evidence_Level": "Mechanistic / preclinical",
    })
    row.update(overrides)
    return row


def _big_catalogue_df(n_noise=300, n_direct=5, n_exploratory=40):
    rows = []
    for i in range(n_direct):
        rows.append(_direct_row(f"Direct_{i}"))
    for i in range(n_exploratory):
        rows.append(_mechanistic_row(f"Explore_{i}"))
    for i in range(n_noise):
        rows.append(_noise_row(f"Noise_{i}"))
    return pd.DataFrame(rows)


# --- Test 1: broad catalogue is pre-screened -------------------------------

def test_broad_catalogue_is_prescreened_to_bounded_pool():
    raw_df = _big_catalogue_df(n_noise=300, n_direct=5, n_exploratory=40)
    pool, audit = prescreen_candidate_universe(
        raw_df, exploratory_budget=10,
    )
    retained_plants = set(pool["Alternative_Plant"])
    # every direct-evidence plant survives
    assert all(f"Direct_{i}" in retained_plants for i in range(5))
    # the bounded pool is much smaller than the full universe
    assert len(retained_plants) < 20
    assert len(retained_plants) < raw_df["Alternative_Plant"].nunique()
    # every catalogue plant has a traceable audit row, retained or not
    assert set(audit["Alternative_Plant"]) == set(raw_df["Alternative_Plant"])
    assert (audit["PreScreen_Status"] == PRESCREEN_STATUS_EXCLUDED).sum() >= 300


# --- Test 2: direct evidence cannot be dropped ------------------------------

def test_direct_evidence_plant_survives_even_below_generic_cap():
    # A generic-looking direct-evidence plant plus far more "stronger
    # looking" (higher shortlist row count) exploratory plants than the
    # budget allows -- direct evidence must never be cut by the lexical cap.
    rows = [_direct_row("Direct_Survivor")]
    for i in range(50):
        rows.append(_mechanistic_row(f"Explore_{i}"))
    raw_df = pd.DataFrame(rows)

    pool, audit = prescreen_candidate_universe(raw_df, exploratory_budget=5)
    assert "Direct_Survivor" in set(pool["Alternative_Plant"])
    row = audit[audit["Alternative_Plant"] == "Direct_Survivor"].iloc[0]
    assert row["PreScreen_Status"] == PRESCREEN_STATUS_SENT


# --- Test 3: Stage 2 novel candidate survives -------------------------------

def test_stage2_novel_candidate_with_sparse_history_reaches_full_scoring():
    raw_df = _big_catalogue_df(n_noise=100, n_direct=2, n_exploratory=5)
    novel = [{"Scientific_Name": "Novel_Sparse_Plant"}]

    pool, audit = prescreen_candidate_universe(
        raw_df, novel_candidate_plants=novel, exploratory_budget=3,
    )
    # The novel plant has no rows at all in the Supabase-catalogue raw_df,
    # yet must still be flagged to reach full scoring via the audit trail.
    novel_rows = audit[audit["Alternative_Plant"] == "Novel_Sparse_Plant"]
    assert len(novel_rows) == 1
    assert novel_rows.iloc[0]["PreScreen_Status"] == PRESCREEN_STATUS_SENT
    assert novel_rows.iloc[0]["Candidate_Source"] == "stage2_novel"


def test_stage2_novel_candidate_already_in_catalogue_marked_both():
    raw_df = pd.DataFrame([_mechanistic_row("Epimedium_sagittatum")])
    novel = [{"Scientific_Name": "Epimedium_sagittatum"}]
    pool, audit = prescreen_candidate_universe(
        raw_df, novel_candidate_plants=novel, exploratory_budget=0,
    )
    row = audit[audit["Alternative_Plant"] == "Epimedium_sagittatum"].iloc[0]
    assert row["PreScreen_Status"] == PRESCREEN_STATUS_SENT
    assert row["Candidate_Source"] == "both"
    assert "Epimedium_sagittatum" in set(pool["Alternative_Plant"])


# --- Test 4: no duplicate full scoring --------------------------------------

def test_commercial_enrichment_does_not_trigger_full_rescore(monkeypatch):
    """Simulates the real Step 5 flow at the composable-function level:
    prescreen -> ONE build_plant_candidate_shortlist() call -> commercial
    enrichment -> rescore_commercial_component(). The expensive full-scoring
    function must be invoked exactly once, never a second time because of
    commercial enrichment.
    """
    raw_df = pd.DataFrame([
        _direct_row("Candidate_A"),
        _direct_row("Candidate_B"),
    ])

    call_count = {"n": 0}
    real_build = build_plant_candidate_shortlist

    def counting_build(*args, **kwargs):
        call_count["n"] += 1
        return real_build(*args, **kwargs)

    monkeypatch.setattr(cs, "build_plant_candidate_shortlist", counting_build)

    pool, _audit = prescreen_candidate_universe(raw_df, exploratory_budget=10)
    summary, _row_audit = cs.build_plant_candidate_shortlist(
        pool, indication="", dosage_form="Capsule", max_candidates=0,
    )
    assert call_count["n"] == 1

    # Simulate commercial enrichment merging Commercial_* fields onto the
    # raw rows for the plants selected for enrichment.
    enriched_raw = raw_df.copy()
    market_plants = _step5_commercial_enrichment_plants(summary)
    assert market_plants  # sanity: something was selected
    for col, value in {
        "Commercial_Novelty_Status": "Commercial white-space",
    }.items():
        enriched_raw[col] = value

    rescored = rescore_commercial_component(summary, enriched_raw, market_plants)

    # The expensive full-scoring function was NEVER called a second time.
    assert call_count["n"] == 1
    # But the score authority still reflects the commercial update.
    assert not rescored.equals(summary) or (rescored["Novelty_Market_Score"] == summary["Novelty_Market_Score"]).all() is False


# --- Test 5: scientific equivalence ------------------------------------------

def test_prescreen_survivor_scores_identically_to_full_universe_scoring():
    raw_df = _big_catalogue_df(n_noise=200, n_direct=3, n_exploratory=10)

    full_summary, _ = build_plant_candidate_shortlist(
        raw_df, indication="", dosage_form="", max_candidates=0,
    )
    pool, _audit = prescreen_candidate_universe(raw_df, exploratory_budget=50)
    bounded_summary, _ = build_plant_candidate_shortlist(
        pool, indication="", dosage_form="", max_candidates=0,
    )

    full_row = full_summary[full_summary["Alternative_Plant"] == "Direct_0"].iloc[0]
    bounded_row = bounded_summary[bounded_summary["Alternative_Plant"] == "Direct_0"].iloc[0]

    assert full_row["Overall_Score"] == bounded_row["Overall_Score"]
    assert full_row["Scientific_Triage_Status"] == bounded_row["Scientific_Triage_Status"]
    assert full_row["Score_Breakdown"] == bounded_row["Score_Breakdown"]


# --- Test 6: irrelevant catalogue plant is not fully scored -----------------

def test_irrelevant_plant_never_enters_scoring_pool():
    raw_df = _big_catalogue_df(n_noise=50, n_direct=1, n_exploratory=0)
    pool, audit = prescreen_candidate_universe(raw_df, exploratory_budget=0)
    assert "Noise_0" not in set(pool["Alternative_Plant"])
    noise_row = audit[audit["Alternative_Plant"] == "Noise_0"].iloc[0]
    assert noise_row["PreScreen_Status"] == PRESCREEN_STATUS_EXCLUDED


# --- Test 7: pre-screen audit -------------------------------------------------

def test_screened_out_plants_retain_traceable_exclusion_reason():
    raw_df = _big_catalogue_df(n_noise=20, n_direct=1, n_exploratory=0)
    _pool, audit = prescreen_candidate_universe(raw_df, exploratory_budget=0)
    excluded = audit[audit["PreScreen_Status"] == PRESCREEN_STATUS_EXCLUDED]
    assert not excluded.empty
    assert excluded["PreScreen_Reason"].map(lambda r: bool(str(r).strip())).all()


# --- Test 8: configurable cap -------------------------------------------------

def test_exploratory_budget_is_configurable_and_preserves_mandatory():
    raw_df = _big_catalogue_df(n_noise=0, n_direct=5, n_exploratory=100)

    pool_small, _ = prescreen_candidate_universe(raw_df, exploratory_budget=5)
    pool_large, _ = prescreen_candidate_universe(raw_df, exploratory_budget=50)

    assert pool_small["Alternative_Plant"].nunique() < pool_large["Alternative_Plant"].nunique()
    # mandatory (direct-evidence) candidates always present regardless of budget
    for pool in (pool_small, pool_large):
        retained = set(pool["Alternative_Plant"])
        assert all(f"Direct_{i}" in retained for i in range(5))


def test_resolve_exploratory_budget_uses_centralized_config():
    assert resolve_exploratory_budget("quick") > 0
    assert resolve_exploratory_budget("full") > resolve_exploratory_budget("quick")
    assert resolve_exploratory_budget(None, override=17) == 17
    # unrecognized mode degrades to the safe default instead of raising
    assert resolve_exploratory_budget("not_a_real_mode") > 0


# --- Test 9: progress events --------------------------------------------------

def test_prescreen_progress_callback_reports_counts():
    raw_df = _big_catalogue_df(n_noise=20, n_direct=2, n_exploratory=5)
    events = []

    def _cb(current, total, message):
        events.append((current, total, message))

    prescreen_candidate_universe(raw_df, exploratory_budget=5, progress_callback=_cb)
    assert events, "prescreen must report at least one progress event"
    assert events[0][1] == raw_df["Alternative_Plant"].nunique()
    # a final event reports the retained/selected count in its message
    assert any("selected" in str(msg).lower() for _c, _t, msg in events)


# --- Test 10: AI/embedding unavailable does not block the funnel -----------

def test_prescreen_and_scoring_have_no_ai_or_network_dependency():
    import stage5_candidate_prescreen as prescreen_module
    forbidden = {"openai", "embedding_service", "llm_client", "llm_extractor"}
    assert not (forbidden & set(dir(prescreen_module)))
    # Runs to completion synchronously with no mocked network/AI client at all.
    raw_df = _big_catalogue_df(n_noise=20, n_direct=2, n_exploratory=5)
    pool, audit = prescreen_candidate_universe(raw_df, exploratory_budget=3)
    summary, _ = build_plant_candidate_shortlist(pool, max_candidates=0)
    assert not summary.empty


# --- _finalize_step5_summary --------------------------------------------------

def test_finalize_resorts_after_commercial_rescore_changes_rank():
    raw_df = pd.DataFrame([
        _direct_row("Low_Novelty", Shared_or_Similar_Compound="alkaloid one"),
        _direct_row("High_Novelty_After_Market", Shared_or_Similar_Compound="alkaloid two"),
    ])
    summary, _ = build_plant_candidate_shortlist(
        raw_df, indication="", dosage_form="", max_candidates=0,
    )
    enriched_raw = raw_df.copy()
    # Give only the second plant a strong commercial white-space signal.
    enriched_raw.loc[
        enriched_raw["Alternative_Plant"] == "High_Novelty_After_Market",
        "Commercial_Novelty_Status",
    ] = "Commercial white-space"

    rescored = rescore_commercial_component(
        summary, enriched_raw, ["Low_Novelty", "High_Novelty_After_Market"],
    )
    finalized = _finalize_step5_summary(rescored)
    top_row = finalized.iloc[0]
    assert top_row["Alternative_Plant"] == "High_Novelty_After_Market"
