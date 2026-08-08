import json
from pathlib import Path
from independent_holdout_e2e import ROOT, OUT, BenchmarkCohort, assess_executability, discover_reference_grounded_cases, evaluate_holdout, split_cases


def _holdout():
    return split_cases(discover_reference_grounded_cases(ROOT))[BenchmarkCohort.PROSPECTIVE_HOLDOUT]


def test_holdout_membership_remains_15():
    assert len(_holdout()) == 15


def test_only_structurally_executable_cases_are_not_gold_seeded():
    ready = [c.case_id for c in _holdout() if assess_executability(c).status == 'EXECUTABLE']
    assert ready == ['refgrounded_001_melissa_officinalis_sleep', 'refgrounded_003_matricaria_chamomilla_sleep']


def test_independent_snapshot_records_do_not_use_gold_reference_ids():
    cases = {c.case_id: c for c in _holdout()}
    for n, cid in [(1, 'refgrounded_001_melissa_officinalis_sleep'), (3, 'refgrounded_003_matricaria_chamomilla_sleep')]:
        snap = json.loads((OUT / 'independent_holdout_snapshots' / f'case_{n:03d}_independent.json').read_text())
        snapshot_ids = {r['reference_id'] for r in snap['records']}
        gold_ids = {gr.reference.reference_id for gr in cases[cid].references}
        assert not snapshot_ids & gold_ids


def test_holdout_scoring_is_one_of_two_before_any_remediation():
    statuses, metrics = evaluate_holdout()
    assert metrics.n_scored == 2
    assert metrics.n_correct == 1
    assert metrics.accuracy == 0.5
    assert len([s for s in statuses if s.status == 'BLOCKED']) == 13


def test_case003_mismatch_is_preserved_not_tuned_away():
    statuses, _ = evaluate_holdout()
    s = next(x for x in statuses if x.case_id == 'refgrounded_003_matricaria_chamomilla_sleep')
    assert s.expected == 'GO WITH CAUTION'
    assert s.actual == 'GO'
    assert s.match is False
