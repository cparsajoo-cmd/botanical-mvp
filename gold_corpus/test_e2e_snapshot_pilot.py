from __future__ import annotations

from end_to_end_validation import FailureStage
from gold_corpus.e2e_snapshot_pilot import (
    PILOT_CASE_NUMBERS,
    load_gold_case,
    load_snapshot,
    run_baseline_case,
    run_case020_irrelevant_source_scenario,
    run_critical_missed_scenario,
    run_duplicate_scenario,
    run_source_unavailable_scenario,
    snapshot_records,
)
from gold_corpus.gold_source_sets import GOLD_SOURCE_SETS


def test_all_seven_snapshots_exist_and_match_gold_critical_sources():
    for number in PILOT_CASE_NUMBERS:
        snapshot = load_snapshot(number)
        case = load_gold_case(number)
        gold = GOLD_SOURCE_SETS[case.case_id]
        snapshot_ids = {r.reference_id for r in snapshot_records(snapshot)}
        assert gold.critical_ids() <= snapshot_ids
        assert all(r.source_url for r in snapshot_records(snapshot))
        assert all(r.source_available for r in snapshot_records(snapshot))


def test_baseline_retrieves_every_critical_source_for_all_pilot_cases():
    for number in PILOT_CASE_NUMBERS:
        result = run_baseline_case(number)
        assert result.source_counts["critical_retrieved"] == result.source_counts["critical_total"]
        assert not any(f.code == "CRITICAL_SOURCE_MISSED" for f in result.failures)


def test_missing_critical_source_fails_closed_for_all_pilot_cases():
    for number in PILOT_CASE_NUMBERS:
        result = run_critical_missed_scenario(number)
        assert any(f.code == "CRITICAL_SOURCE_MISSED" for f in result.failures)


def test_unavailable_critical_source_is_not_treated_as_clearance():
    for number in PILOT_CASE_NUMBERS:
        result = run_source_unavailable_scenario(number)
        assert any(f.stage == FailureStage.SOURCE_UNAVAILABLE for f in result.failures)
        assert any(f.code == "CRITICAL_SOURCE_MISSED" for f in result.failures)


def test_duplicate_capture_is_deduplicated_by_article_identity():
    result = run_duplicate_scenario(21)
    assert result.source_counts["duplicates"] >= 1


def test_real_irrelevant_echinacea_root_source_is_counted_as_irrelevant_for_herb_case():
    result = run_case020_irrelevant_source_scenario()
    assert result.source_counts["known_irrelevant_retrieved"] == 1
