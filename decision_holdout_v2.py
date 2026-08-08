from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from end_to_end_validation import RetrievedEvidence, ValidationQuestion, _build_plant_df, _norm_taxon
from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from decision_benchmark_v1 import compute_metrics
from scientific_decision_validation import DecisionComparison

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'gold_corpus'/'decision_holdout_v2'

def load_reference():
    return json.loads((BASE/'frozen_reference_labels.json').read_text())

def run_case(case):
    snap=json.loads((BASE/'snapshots'/f"{case['case_id']}.json").read_text())
    q=ValidationQuestion(**snap['question'])
    recs=[RetrievedEvidence(**r) for r in snap['records']]
    ev=pd.DataFrame([r.to_engine_row(q.indication,q.dosage_form,q.market) for r in recs])
    # This frozen v2 snapshot predates canonical structured result_direction
    # coverage.  It is now regression-only (the labels have been exposed), so
    # opt in explicitly to the legacy per-record text fallback rather than
    # weakening the production engine's fail-safe default.
    engine=BotanicalRDCandidateEngine(
        plant_compounds_df=_build_plant_df(snap['candidate_pool'],q.indication),
        compound_profiles_df=pd.DataFrame(), scientific_evidence_df=pd.DataFrame(),
        evidence_df=ev, use_live_search=False, allow_legacy_text_fallback=True,
    )
    out=engine.run(indication=q.indication,dosage_form=q.dosage_form,market=q.market)
    target=_norm_taxon(case['botanical'])
    row=out[out['Alternative_Plant'].map(_norm_taxon)==target].iloc[0]
    return final_status_from_engine_row(row), row

def evaluate():
    refs=load_reference()['cases']; comps=[]; rows=[]
    for c in refs:
        actual,row=run_case(c); expected=FinalDecisionStatus(c['expected'])
        comps.append(DecisionComparison(c['case_id'],expected,actual,expected==actual))
        rows.append({'case_id':c['case_id'],'expected':expected.value,'actual':actual.value,'match':expected==actual,'score':float(row.get('Botanical_RD_Score',0))})
    return rows, compute_metrics(comps)

if __name__=='__main__':
    rows,metrics=evaluate()
    payload={'version':'decision-holdout-v2/1.0.0','rows':rows,'metrics':asdict(metrics)}
    (BASE/'results.json').write_text(json.dumps(payload,indent=2,default=str))
    print(json.dumps(payload,indent=2,default=str))
