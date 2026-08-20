"""Regression test for the Step 2 wall-clock collection budgets.

CONTEXT -- two related, but distinct, production incidents on the same
feature, fixed in sequence:

INCIDENT 1 (outer per-wave scheduling budget): for an 8-candidate run (the
default global_candidate_count) without pilot_mode, 3 of 8 plants (the ones
scheduled into later worker waves, since plant_workers=2) consistently came
back with retrieval_coverage_status == INCOMPLETE, even though nothing was
wrong with those plants' evidence -- research_engine.py's own outer
wall-clock budget (previously max(105, worker_waves * 35) = 140s for 4
waves) expired before their wave finished, so they were marked
collection_finished=False. Root cause: research_engine.py hardcoded its own
guess at "how long one plant's collection can take" (35s/wave), completely
independent of multi_source_collector.py's actual internal ceiling for that
same call (TOTAL_TIME_BUDGET, then 30s) -- the two constants had already
drifted apart, leaving almost no headroom.

INCIDENT 2 (inner per-plant collection budget): after fixing incident 1 and
giving every wave enough outer wall-clock time to actually run to
completion, a real run against live sources came back with 0 saved records
and every one of 8 plants marked INCOMPLETE. The evidence-collection error
export showed NCBI PubMed returning real HTTP 429 (rate limited) for every
plant, and every one of the other 13-14 sources for that same plant showing
"Timed out after 30s (overall budget, not this source alone)" -- i.e. they
never got a chance to even start. Verified against the code: there are 15
enabled sources (source_registry.get_enabled_sources()) but only
MAX_WORKERS=6 run concurrently inside multi_source_collector.py, so a
plant needs ceil(15/6)=3 sequential waves of source calls in the worst
case; individual connector calls use a 20s HTTP timeout, and
openalex_connector.py / semantic_scholar_connector.py additionally retry
with backoff on 429. The (then) 30s TOTAL_TIME_BUDGET was never enough for
3 such waves, so most sources for most plants were abandoned before they
ever ran -- not because anything was actually broken.

THE FIX: TOTAL_TIME_BUDGET is now a real module-level constant in
multi_source_collector.py (60s, derived from the above), and
research_engine.py imports it and derives its own outer per-wave budget
FROM it (TOTAL_TIME_BUDGET + a fixed scheduling-jitter margin), instead of
hardcoding a second, independently-tuned number. This closes both
incidents and makes it structurally impossible for the two budgets to
silently drift apart again.

HOW TO RUN
    pytest -q test_step2_collection_budget.py
"""
import research_engine as re_mod
from multi_source_collector import TOTAL_TIME_BUDGET, MAX_WORKERS
import source_registry as sr

_JITTER_MARGIN_SECONDS = 15
PER_PLANT_WORST_CASE_SECONDS = TOTAL_TIME_BUDGET


def _mock_pipeline(monkeypatch, candidate_plants):
    """Patch every network-touching function used by run_research_engine."""
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


# ---------------------------------------------------------------------
# Inner budget (multi_source_collector.TOTAL_TIME_BUDGET)
# ---------------------------------------------------------------------

def test_inner_budget_covers_worst_case_source_fanout():
    # 15 enabled sources through MAX_WORKERS=6 concurrent slots needs
    # ceil(15/6) = 3 sequential waves; each connector's own HTTP timeout is
    # 20s (verified in the connector modules), so a plant genuinely can
    # need up to 3 * 20 = 60s when several sources are slow/rate-limited.
    num_sources = len(sr.get_enabled_sources())
    source_waves = -(-num_sources // MAX_WORKERS)  # ceil
    connector_timeout_seconds = 20
    worst_case = source_waves * connector_timeout_seconds

    assert TOTAL_TIME_BUDGET >= worst_case, (
        f"TOTAL_TIME_BUDGET ({TOTAL_TIME_BUDGET}s) must cover the "
        f"{worst_case}s worst case for {num_sources} sources across "
        f"{source_waves} waves of {MAX_WORKERS} concurrent workers, or "
        "most sources will be abandoned before they ever run."
    )


# ---------------------------------------------------------------------
# Outer budget (research_engine.py) -- derived from the inner one
# ---------------------------------------------------------------------

def test_eight_candidate_non_pilot_run_has_headroom_over_worst_case(monkeypatch):
    _mock_pipeline(monkeypatch, _EIGHT_PLANTS)

    result = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion",
        indication="TestIndication", target_market="EU",
        global_candidate_count=8, pilot_mode=False,
    )

    budget = result["candidate_discovery_diagnostics"]["collection_time_budget_seconds"]

    plant_workers = 2
    worker_waves = -(-8 // plant_workers)  # ceil(8 / 2) = 4
    worst_case_seconds = worker_waves * PER_PLANT_WORST_CASE_SECONDS

    assert budget > worst_case_seconds, (
        f"Step 2 outer budget ({budget}s) must exceed the "
        f"{worst_case_seconds}s worst-case wall clock for {worker_waves} "
        f"waves of {plant_workers} concurrent plants at "
        f"{PER_PLANT_WORST_CASE_SECONDS}s each, or later-wave plants will "
        "be wrongly marked INCOMPLETE."
    )


def test_outer_budget_is_derived_from_the_inner_constant(monkeypatch):
    # Locks in the actual fix for incident 1: the outer per-wave budget is
    # a function of TOTAL_TIME_BUDGET, not an independently-chosen number
    # that can quietly fall out of sync with it again.
    for candidate_plants in (_EIGHT_PLANTS, _EIGHT_PLANTS[:4]):
        _mock_pipeline(monkeypatch, candidate_plants)

        budget = re_mod.run_research_engine(
            product_type="Food supplement", dosage_form="Infusion",
            indication="TestIndication", target_market="EU",
            global_candidate_count=len(candidate_plants), pilot_mode=False,
        )["candidate_discovery_diagnostics"]["collection_time_budget_seconds"]

        plant_workers = 2
        worker_waves = -(-len(candidate_plants) // plant_workers)
        expected = max(180, worker_waves * (TOTAL_TIME_BUDGET + _JITTER_MARGIN_SECONDS))

        assert budget == expected, (
            f"Outer budget ({budget}s) is not derived from TOTAL_TIME_BUDGET "
            f"({TOTAL_TIME_BUDGET}s) as expected ({expected}s) for "
            f"{len(candidate_plants)} candidates -- the two budgets may "
            "have drifted apart again."
        )


def test_non_pilot_budget_is_never_smaller_than_pilot(monkeypatch):
    # Non-pilot mode does strictly more per-source work than pilot_mode
    # (full max_results vs. PILOT_MAX_RESULTS), so it must never receive a
    # smaller time allowance than the lighter pilot run, at any candidate count.
    for candidate_plants in (_EIGHT_PLANTS, _EIGHT_PLANTS[:3]):
        _mock_pipeline(monkeypatch, candidate_plants)

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
    _mock_pipeline(monkeypatch, ["Solo Plant"])

    result = re_mod.run_research_engine(
        product_type="Food supplement", dosage_form="Infusion",
        indication="TestIndication", target_market="EU",
        global_candidate_count=1, pilot_mode=False,
    )

    budget = result["candidate_discovery_diagnostics"]["collection_time_budget_seconds"]
    assert budget >= PER_PLANT_WORST_CASE_SECONDS + 30
