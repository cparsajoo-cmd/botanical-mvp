"""Regression tests for the Step 2 wall-clock collection budget and source
concurrency.

CONTEXT -- three related, but distinct, production incidents on the same
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

INCIDENT 2 (fixed worker cap serializing independent sources into waves):
after fixing incident 1, a real run against live sources still came back
with 0 saved records and every one of 8 plants marked INCOMPLETE, with
nearly every source (13-14 of 15) showing "Timed out after 30s (then 60s)
(overall budget, not this source alone)" -- meaning they never even started.
Root cause verified against the code: MAX_WORKERS was a fixed cap of 6, so
15 independent sources (different domains, no shared resource -- pure
I/O-bound HTTP calls) were forced through ceil(15/6)=3 sequential waves per
plant. Sources queued behind slow/rate-limited ones never got a worker slot
before the overall budget expired, no matter how large that budget was made
(30s, then 60s -- both still failed the same way).

INCIDENT 3 (the actual fix): max_workers is now set per-call to the number
of enabled sources, so every source runs concurrently in one wave instead
of being serialized into artificial rounds. Wall-clock time is now bounded
by the single slowest source (worst case: one connector's 20s HTTP timeout
plus the retry-with-backoff loop in openalex_connector.py /
semantic_scholar_connector.py on real HTTP 429s, observed in production
alongside genuine NCBI PubMed rate-limiting), not by (sources / a fixed
worker cap) sequential rounds of that. TOTAL_TIME_BUDGET was re-derived
down to 45s accordingly, and research_engine.py's outer per-wave budget is
imported/derived from it (TOTAL_TIME_BUDGET + a fixed jitter margin)
instead of a second, independently-tuned number, so none of these three can
silently drift apart again.

HOW TO RUN
    pytest -q test_step2_collection_budget.py
"""
import research_engine as re_mod
import multi_source_collector as msc
from multi_source_collector import TOTAL_TIME_BUDGET
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
# Incident 2/3: source concurrency -- no more fixed worker cap
# ---------------------------------------------------------------------

def test_all_enabled_sources_run_in_a_single_concurrent_wave(monkeypatch):
    """Locks in the actual fix for incident 2: the ThreadPoolExecutor used
    inside collect_multi_source_evidence() must be sized to run every
    enabled source at once, not queue most of them behind a small fixed
    cap."""
    captured_max_workers = {}

    class _FakeExecutor:
        def __init__(self, max_workers=None):
            captured_max_workers["value"] = max_workers

        def submit(self, fn, *args, **kwargs):
            class _ImmediateFuture:
                def result(self_inner, timeout=None):
                    return [], []
                def done(self_inner):
                    return True
            return _ImmediateFuture()

        def shutdown(self, wait=True, cancel_futures=False):
            pass

    monkeypatch.setattr(msc, "ThreadPoolExecutor", _FakeExecutor)
    monkeypatch.setattr(
        msc, "as_completed", lambda future_map, timeout=None: list(future_map)
    )

    msc.collect_multi_source_evidence(
        scientific_name="Test Plant",
        indication="TestIndication",
        dosage_form="Infusion",
        save=False,
    )

    num_enabled_sources = len(sr.get_enabled_sources())
    assert captured_max_workers["value"] >= num_enabled_sources, (
        f"collect_multi_source_evidence used max_workers="
        f"{captured_max_workers['value']}, which is fewer than the "
        f"{num_enabled_sources} enabled sources -- sources will again be "
        "serialized into waves and queued sources can time out before "
        "they ever start."
    )


def test_inner_budget_covers_single_wave_worst_case():
    # With every source running concurrently (no more wave queueing), the
    # dominant worst case is a single connector's 20s HTTP timeout plus a
    # realistic retry-with-backoff allowance for the flakiest connectors
    # (openalex_connector.py / semantic_scholar_connector.py on HTTP 429).
    connector_timeout_seconds = 20
    retry_backoff_allowance_seconds = 15
    worst_case = connector_timeout_seconds + retry_backoff_allowance_seconds

    assert TOTAL_TIME_BUDGET >= worst_case, (
        f"TOTAL_TIME_BUDGET ({TOTAL_TIME_BUDGET}s) must cover the "
        f"{worst_case}s single-wave worst case (20s connector timeout + "
        f"{retry_backoff_allowance_seconds}s retry/backoff allowance)."
    )


# ---------------------------------------------------------------------
# Incident 1: outer budget (research_engine.py) -- derived from the inner one
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
