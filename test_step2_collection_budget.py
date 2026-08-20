"""Regression test for the Step 2 per-wave wall-clock collection budget.

CONTEXT
Reported symptom: for an 8-candidate run (the default global_candidate_count)
without pilot_mode, 3 of 8 plants (the ones scheduled into the later worker
waves, since plant_workers=2) consistently came back with
retrieval_coverage_status == INCOMPLETE, even though nothing was actually
wrong with those plants' evidence -- Step 2's own outer wall-clock budget
(previously max(105, worker_waves * 35) = 140s for 4 waves) expired before
their wave finished, so they were marked collection_finished=False.

Root cause (verified against the code, not assumed): each single plant's
own collect_multi_source_evidence() call has an internal worst-case budget
of multi_source_collector.TOTAL_TIME_BUDGET = SOURCE_TIMEOUT_SECONDS * 2 =
30s. The previous non-pilot per-wave allowance of 35s left only ~5s of
headroom over that 30s worst case -- not enough to absorb normal scheduling
or network jitter across a wave. Non-pilot mode also does strictly more
per-source work than pilot_mode (full max_results vs. the reduced
PILOT_MAX_RESULTS scope), so it should never have had a *smaller* budget
than pilot_mode (35s/wave & 105s floor vs. pilot's 45s/wave & 180s floor)
-- but it did.

This test locks in the fix: pilot_mode and non-pilot now share a single
budget formula (max(180, worker_waves * 45)), so an 8-candidate non-pilot
run gets a total budget with real headroom over the 8-plant/2-worker/
30s-per-plant worst case (4 waves * 30s = 120s), and the two modes can't
drift apart again.

HOW TO RUN
    pytest -q test_step2_collection_budget.py
"""
import research_engine as re_mod
from multi_source_collector import SOURCE_TIMEOUT_SECONDS

PER_PLANT_WORST_CASE_SECONDS = SOURCE_TIMEOUT_SECONDS * 2  # mirrors TOTAL_TIME_BUDGET


def _mock_pipeline(monkeypatch, candidate_plants, captured_budgets):
    """Patch every network-touching function used by run_research_engine,
    and capture the Step 2 per-wave budget actually used for this run via
    the returned discovery diagnostics (no private attribute access)."""
    monkeypatch.setattr(
        re_mod, "collect_multi_source_evidence",
        lambda **kwargs: {"saved_records": [], "errors": [], "sources_checked": []},
    )
    monkeypatch.setattr(
        re_mod, "_richer_candidate_plants",
        lambda indication, dosage_form, target_market, target_count: list(candidate_plants),
    )
    monkeypatch.setattr(
        re_mod, "_online_discovered_candidate_plants",
        lambda indication, dosage_form, target_market, target_count, seed_plants=None: (
            [], {"connector_errors": [], "ranked_matches": {}},
        ),
    )


_EIGHT_PLANTS = [f"Plant species {i}" for i in range(8)]


def test_eight_candidate_non_pilot_run_has_headroom_over_worst_case(monkeypatch):
    _mock_pipeline(monkeypatch, _EIGHT_PLANTS, {})

    result = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion",
        indication="TestIndication", target_market="EU",
        global_candidate_count=8, pilot_mode=False,
    )

    diagnostics = result["candidate_discovery_diagnostics"]
    budget = diagnostics["collection_time_budget_seconds"]

    plant_workers = 2
    worker_waves = -(-8 // plant_workers)  # ceil(8 / 2) = 4
    worst_case_seconds = worker_waves * PER_PLANT_WORST_CASE_SECONDS  # 4 * 30 = 120

    assert budget > worst_case_seconds, (
        f"Step 2 budget ({budget}s) must exceed the {worst_case_seconds}s "
        "worst-case wall clock for 4 waves of 2 concurrent plants at 30s "
        "each, or later-wave plants will be wrongly marked INCOMPLETE."
    )


def test_non_pilot_budget_is_never_smaller_than_pilot(monkeypatch):
    # Non-pilot mode does strictly more per-source work than pilot_mode
    # (full max_results vs. PILOT_MAX_RESULTS), so it must never receive a
    # smaller time allowance than the lighter pilot run, at any candidate count.
    for candidate_plants in (_EIGHT_PLANTS, _EIGHT_PLANTS[:3]):
        captured = {}
        _mock_pipeline(monkeypatch, candidate_plants, captured)

        non_pilot = re_mod.run_research_engine(
            product_type="Food supplement", dosage_form="Infusion",
            indication="TestIndication", target_market="EU",
            global_candidate_count=len(candidate_plants), pilot_mode=False,
        )["candidate_discovery_diagnostics"]["collection_time_budget_seconds"]

        pilot = re_mod.run_research_engine(
            product_type="Food supplement", dosage_form="Infusion",
            indication="TestIndication", target_market="EU",
            global_candidate_count=len(candidate_plants), pilot_mode=True,
        )["candidate_discovery_diagnostics"]["collection_time_budget_seconds"]

        assert non_pilot >= pilot, (
            f"non-pilot budget ({non_pilot}s) fell below pilot budget "
            f"({pilot}s) for {len(candidate_plants)} candidates; non-pilot "
            "does more work per source and must not get less time."
        )


def test_single_plant_run_still_gets_a_reasonable_floor(monkeypatch):
    _mock_pipeline(monkeypatch, ["Solo Plant"], {})

    result = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion",
        indication="TestIndication", target_market="EU",
        global_candidate_count=1, pilot_mode=False,
    )

    budget = result["candidate_discovery_diagnostics"]["collection_time_budget_seconds"]
    assert budget >= PER_PLANT_WORST_CASE_SECONDS + 30
