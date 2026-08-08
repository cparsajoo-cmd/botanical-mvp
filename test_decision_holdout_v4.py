import json
from decision_holdout_v4 import BASE, load_reference, evaluate

def test_holdout_v4_is_frozen_and_uses_distinct_reference_pmids():
    data=load_reference(); assert data['version']=='decision-holdout-v4/1.0.0'; assert len(data['cases'])==10
    for c in data['cases']:
        snap=json.loads((BASE/'snapshots'/f"{c['case_id']}.json").read_text()); engine_pmids={r.get('pmid') for r in snap['records']}; assert c['reference_pmid'] not in engine_pmids

def test_holdout_v4_runner_scores_all_frozen_cases():
    rows,metrics=evaluate(); assert len(rows)==10; assert metrics.n_scored==10
