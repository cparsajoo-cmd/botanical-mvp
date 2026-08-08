import json
from pathlib import Path
from decision_holdout_v3 import evaluate, load_reference

BASE=Path(__file__).parent/'gold_corpus'/'decision_holdout_v3'

def test_holdout_v3_is_frozen_and_uses_distinct_reference_pmids():
    data=load_reference()
    assert data['version']=='decision-holdout-v3/1.0.0'
    assert len(data['cases'])==5
    for c in data['cases']:
        snap=json.loads((BASE/'snapshots'/f"{c['case_id']}.json").read_text())
        engine_pmids={str(r.get('pmid') or '') for r in snap['records']}
        assert c['reference_pmid'] not in engine_pmids

def test_holdout_v3_runner_scores_all_frozen_cases():
    rows,metrics=evaluate()
    assert len(rows)==5
    assert metrics.n_scored==5
    assert {r['case_id'] for r in rows}=={c['case_id'] for c in load_reference()['cases']}
