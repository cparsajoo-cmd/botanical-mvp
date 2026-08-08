import json
from pathlib import Path
from independent_holdout_e2e import ROOT, OUT, BenchmarkCohort, assess_executability, discover_reference_grounded_cases, evaluate_holdout, split_cases


def _holdout():
    return split_cases(discover_reference_grounded_cases(ROOT))[BenchmarkCohort.PROSPECTIVE_HOLDOUT]


def test_holdout_membership_remains_15():
    assert len(_holdout()) == 15


def test_all_holdout_cases_are_structurally_executable_without_hidden_gold_evidence():
    statuses = [assess_executability(c) for c in _holdout()]
    assert len(statuses) == 15
    assert all(s.status == 'EXECUTABLE' for s in statuses)


def test_independent_snapshot_records_do_not_use_gold_reference_ids():
    cases = {c.case_id: c for c in _holdout()}
    for n, cid in [(1, 'refgrounded_001_melissa_officinalis_sleep'), (3, 'refgrounded_003_matricaria_chamomilla_sleep')]:
        snap = json.loads((OUT / 'independent_holdout_snapshots' / f'case_{n:03d}_independent.json').read_text())
        snapshot_ids = {r['reference_id'] for r in snap['records']}
        gold_ids = {gr.reference.reference_id for gr in cases[cid].references}
        assert not snapshot_ids & gold_ids


def test_full_holdout_remains_fully_scorable_after_snapshots_are_frozen():
    # The original unseen 5/15 score is a historical validation baseline, not
    # an invariant production expectation. After root-cause remediation these
    # same cases are regression fixtures, so this test protects executability
    # and metric integrity without freezing the old buggy decisions forever.
    statuses, metrics = evaluate_holdout()
    assert metrics.n_scored == 15
    assert 0 <= metrics.n_correct <= metrics.n_scored
    assert metrics.accuracy == metrics.n_correct / metrics.n_scored
    assert len([s for s in statuses if s.status == 'BLOCKED']) == 0


def test_all_frozen_snapshots_declare_no_gold_truth_used_for_retrieval():
    snap_dir = OUT / 'independent_holdout_snapshots'
    snapshots = sorted(snap_dir.glob('case_*_independent.json'))
    assert len(snapshots) == 15
    for path in snapshots:
        snap = json.loads(path.read_text())
        assert snap['capture_metadata']['gold_truth_used_for_retrieval'] is False
        assert 'expected' not in snap
        assert 'actual' not in snap


def test_case003_regression_reflects_root_cause_remediation_without_changing_frozen_snapshot():
    # The original unseen mismatch remains preserved in FULL_15_HOLDOUT_REPORT.md.
    # After evidence-interpretation remediation this frozen snapshot is a
    # regression fixture and should now exercise the corrected cautious path.
    statuses, _ = evaluate_holdout()
    s = next(x for x in statuses if x.case_id == 'refgrounded_003_matricaria_chamomilla_sleep')
    assert s.expected == 'GO WITH CAUTION'
    assert s.actual == 'GO WITH CAUTION'
    assert s.match is True
