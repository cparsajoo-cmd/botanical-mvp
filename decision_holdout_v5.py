from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine, DECISION_ENGINE_VERSION
from end_to_end_validation import RetrievedEvidence, ValidationQuestion, _build_plant_df, _norm_taxon
from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from decision_benchmark_v1 import compute_metrics
from scientific_decision_validation import DecisionComparison
from validation_provenance import DatasetStatus, persist_validation_run
from validation_risk_metrics import compute_high_risk_metrics_from_confusion_matrix

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'gold_corpus'/'decision_holdout_v5'

def load_reference():
    return json.loads((BASE/'frozen_reference_labels.json').read_text())

def run_case(case):
    snap=json.loads((BASE/'snapshots'/f"{case['case_id']}.json").read_text())
    q=ValidationQuestion(**snap['question'])
    recs=[RetrievedEvidence(**r) for r in snap['records']]
    ev=pd.DataFrame([r.to_engine_row(q.indication,q.dosage_form,q.market) for r in recs])
    # Isolation fix (2026-08-11): evidence_records_df was never pinned here,
    # so the engine silently fetched the real, live production
    # `evidence_records` table instead of an empty frame -- breaking this
    # holdout's seal (see run_final_reference_holdout_v1.py's 2026-08-11
    # comment for the full mechanism).
    engine=BotanicalRDCandidateEngine(
        plant_compounds_df=_build_plant_df(snap['candidate_pool'],q.indication),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_records_df=pd.DataFrame(),
        evidence_df=ev,
        use_live_search=False,
    )
    out=engine.run(indication=q.indication,dosage_form=q.dosage_form,market=q.market)
    target=_norm_taxon(case['botanical'])
    row=out[out['Alternative_Plant'].map(_norm_taxon)==target].iloc[0]
    return final_status_from_engine_row(row),row

def evaluate():
    refs=load_reference()['cases']; comps=[]; rows=[]
    for c in refs:
        actual,row=run_case(c)
        expected=FinalDecisionStatus(c['expected'])
        comps.append(DecisionComparison(c['case_id'],expected,actual,expected==actual))
        rows.append({'case_id':c['case_id'],'expected':expected.value,'actual':actual.value,
                     'match':expected==actual,'score':float(row.get('Botanical_RD_Score',0))})
    return rows,compute_metrics(comps)

if __name__=='__main__':
    rows,metrics=evaluate()
    metrics_dict=asdict(metrics)
    payload={'version':'decision-holdout-v5/1.0.0','engine_version':DECISION_ENGINE_VERSION,'rows':rows,'metrics':metrics_dict}
    high_risk=compute_high_risk_metrics_from_confusion_matrix(metrics_dict['confusion_matrix'], n_scored=metrics_dict.get('n_scored')).to_dict()
    artifact,registry,_=persist_validation_run(
        repo_root=ROOT, dataset_name='decision_holdout_v5', dataset_version='1.0.0',
        dataset_status=DatasetStatus.REGRESSION, engine_version=DECISION_ENGINE_VERSION,
        result_payload=payload, labels_visible_before_execution=True,
        results_previously_inspected=True, used_for_remediation=True,
        run_kind='post_remediation_rerun',
        overall_result={'n_scored':metrics_dict.get('n_scored'),'n_correct':metrics_dict.get('n_correct'),'accuracy':metrics_dict.get('accuracy'),'macro_f1':metrics_dict.get('macro_f1')},
        per_class_metrics=metrics_dict.get('per_class_recall') or {},
        safety_regulatory_metrics=high_risk, historical_blind_result_path='gold_corpus/decision_holdout_v5/blind_run_historical_result.json',
        notes='This execution is regression-only because the reference labels and prior results have already been exposed.'
    )
    payload['immutable_output_artifact']=artifact.relative_to(ROOT).as_posix()
    payload['validation_registry']=registry.relative_to(ROOT).as_posix()
    print(json.dumps(payload,indent=2,default=str))
