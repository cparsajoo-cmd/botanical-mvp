
from pathlib import Path
import json, pandas as pd
from dataclasses import asdict
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine, DECISION_ENGINE_VERSION
from end_to_end_validation import _build_plant_df, _norm_taxon
from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from scientific_decision_validation import DecisionComparison
from decision_benchmark_v1 import compute_metrics
from scientific_validity_release_gate import ReferenceValidationProtocol, evaluate_reference_grounded_release

ROOT=Path(__file__).resolve().parent
BASE=ROOT/"gold_corpus/scientific_validity/final_holdout_v1"

def to_row(r, indication):
    return {
        "Evidence_Record_ID":r["reference_id"],"Scientific_Name":r["scientific_name"],
        "Target_Indication":r.get("target_indication") or indication,"Dosage_Form":"oral","Target_Market":"EU",
        "Notes":r["notes"],"Source_Type":r.get("source_type",""),"Source_Title":r.get("source_title",""),
        "Source_URL":r.get("source_url",""),"PMID":r.get("pmid",""),"Study_Type":r.get("study_design",""),
        "Evidence_Level":r.get("evidence_quality",""),"Source_Authority":r.get("source_authority",""),
        "Source_Year":r.get("publication_year",""),"Primary_Outcome":r.get("primary_outcome",""),
        "Comparator":r.get("comparator",""),"Risk_of_Bias":r.get("risk_of_bias",""),
    }

refs=json.loads((BASE/"frozen_reference_labels.json").read_text())["cases"]
rows=[]; comps=[]
for c in refs:
    snap=json.loads((BASE/"snapshots"/f"{c['case_id']}.json").read_text())
    ev=pd.DataFrame([to_row(r,c["indication"]) for r in snap["records"]])
    engine=BotanicalRDCandidateEngine(
        plant_compounds_df=_build_plant_df(snap["candidate_pool"],c["indication"]),
        compound_profiles_df=pd.DataFrame(),scientific_evidence_df=pd.DataFrame(),
        evidence_df=ev,use_live_search=False)
    out=engine.run(indication=c["indication"],dosage_form="oral",market="EU")
    target=_norm_taxon(c["botanical"])
    tr=out[out["Alternative_Plant"].map(_norm_taxon)==target]
    actual=None if tr.empty else final_status_from_engine_row(tr.iloc[0])
    expected=FinalDecisionStatus(c["expected"])
    match=actual==expected
    rows.append({"case_id":c["case_id"],"botanical":c["botanical"],"expected":expected.value,
                 "actual":None if actual is None else actual.value,"match":match})
    comps.append(DecisionComparison(c["case_id"],expected,actual,match))

metrics=compute_metrics(comps)
payload={"version":"reference-grounded-final-holdout-v1/1.0.0","engine_version":DECISION_ENGINE_VERSION,
         "rows":rows,"metrics":asdict(metrics)}
(BASE/"blind_results.json").write_text(json.dumps(payload,indent=2,default=str))

class_support={}
source_support={}
for c in refs:
    class_support[c["expected"]]=class_support.get(c["expected"],0)+1
    source_support[c["case_id"]]=1
protocol=ReferenceValidationProtocol(
    benchmark_id="reference-grounded-final-holdout-v1",
    reference_frozen_before_engine_run=True,engine_blinded_to_reference_labels=True,
    remediation_cases_excluded=True,reference_evidence_excluded_from_engine_input=True,
    provenance_complete=True,n_cases=len(refs),class_support=class_support,
    reference_source_support=source_support)
gate=evaluate_reference_grounded_release(protocol,metrics)
gate_payload={"releasable":gate.releasable,"claim":gate.claim,"blockers":list(gate.blockers),"warnings":list(gate.warnings)}
(BASE/"release_gate_result.json").write_text(json.dumps(gate_payload,indent=2))
print(json.dumps({"engine_version":DECISION_ENGINE_VERSION,"rows":rows,"metrics":asdict(metrics),"gate":gate_payload},indent=2,default=str))
