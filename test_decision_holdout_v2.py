from decision_holdout_v2 import evaluate, load_reference

def test_holdout_has_five_frozen_cases_and_distinct_reference_engine_pmids():
    refs=load_reference()['cases']
    assert len(refs)==5
    for c in refs:
        import json
        from decision_holdout_v2 import BASE
        snap=json.loads((BASE/'snapshots'/f"{c['case_id']}.json").read_text())
        engine_pmids={r.get('pmid') for r in snap['records']}
        assert c['reference_pmid'] not in engine_pmids

def test_fresh_holdout_executes_all_cases():
    rows,metrics=evaluate()
    assert len(rows)==5
    assert all(r['actual'] for r in rows)
