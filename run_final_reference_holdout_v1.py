"""Runs one Reference-Grounded Validation case set (v1, v2, or v3) against
the current engine code. v1/v2 are REGRESSION checks (see below); v3 is
the genuine BLIND holdout, added 2026-08-11 -- see the freeze note further
down before running it.

BUG FOUND (2026-08-10): the original version of this script always read
gold_corpus/scientific_validity/final_holdout_v1/frozen_reference_labels.json
and always wrote blind_results.json / release_gate_result.json under the
SAME unversioned filenames, for both the v1 and v2 case sets. When v2 was
run, it silently overwrote v1's frozen expected-labels file and v1's
result artifacts -- v1's raw evidence snapshots (gold_corpus/.../snapshots/
rgv1_*.json) survived, but v1's frozen "correct answer" for each case did
not, and was only recovered because Hamid found an older commit of that
file on GitHub. v1's original blind_results.json/release_gate_result.json
were NOT recoverable and are gone for good.

Fix: --tag is now required and selects both the input labels file
(frozen_reference_labels_<tag>.json) and the output filenames
(blind_results_<tag>.json, release_gate_result_<tag>.json), so running one
case set can never again silently destroy the other's frozen labels or
results. There is no default tag -- an explicit choice is required every
time this script runs.

Per the holdout integrity rule (see FINAL_REFERENCE_GROUNDED_VALIDATION_
V2_REPORT.md): v1 and v2 are EXPOSED. Their output is a regression check
on already-seen cases, never an independent/blind validity estimate.

v3 (2026-08-11): a genuinely independent 20-case holdout -- zero overlap
with v1/v2, gold_cases/, or decision_holdout_v2 through v5 (80 species
checked programmatically; see FREEZE_MANIFEST_v3.json). Frozen before
this script was ever run against it. --tag v3 is the one case where this
script's output is a real blind validation, not a regression check --
but ONLY if the freeze integrity check (verify_rgv3_freeze.py) passes
first; the GitHub Actions workflow runs that check as a required prior
step and refuses to proceed on any mismatch. Per the project's holdout
integrity rule: if v3's result is weak, report it as weak -- do not add
vocabulary, change a label, drop a case, tune a threshold, or add a
special-case rule in response to seeing this output. Any such change
would require freezing an entirely new holdout first.
"""
import argparse
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tag",
        required=True,
        choices=["v1", "v2", "v3"],
        help="Which exposed case set to run as a regression check. Required "
        "(no default) so v1 and v2 can never again silently overwrite each "
        "other's frozen labels or results -- see the 2026-08-10 note above.",
    )
    args = ap.parse_args()
    tag = args.tag

    labels_path = BASE / f"frozen_reference_labels_{tag}.json"
    if not labels_path.exists():
        raise SystemExit(
            f"Missing {labels_path}. This is the frozen expected-answer file "
            f"for case set '{tag}' -- it must exist and must not be "
            "reconstructed from memory or from aggregate report numbers."
        )

    refs=json.loads(labels_path.read_text())["cases"]
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
    payload={"version":f"reference-grounded-final-holdout-{tag}/1.0.0","engine_version":DECISION_ENGINE_VERSION,
             "rows":rows,"metrics":asdict(metrics)}
    (BASE/f"blind_results_{tag}.json").write_text(json.dumps(payload,indent=2,default=str))

    class_support={}
    source_support={}
    for c in refs:
        class_support[c["expected"]]=class_support.get(c["expected"],0)+1
        source_support[c["case_id"]]=1
    protocol=ReferenceValidationProtocol(
        benchmark_id=f"reference-grounded-final-holdout-{tag}",
        reference_frozen_before_engine_run=True,engine_blinded_to_reference_labels=True,
        remediation_cases_excluded=True,reference_evidence_excluded_from_engine_input=True,
        provenance_complete=True,n_cases=len(refs),class_support=class_support,
        reference_source_support=source_support)
    gate=evaluate_reference_grounded_release(protocol,metrics)
    gate_payload={"releasable":gate.releasable,"claim":gate.claim,"blockers":list(gate.blockers),"warnings":list(gate.warnings)}
    (BASE/f"release_gate_result_{tag}.json").write_text(json.dumps(gate_payload,indent=2))
    print(json.dumps({"tag":tag,"engine_version":DECISION_ENGINE_VERSION,"rows":rows,"metrics":asdict(metrics),"gate":gate_payload},indent=2,default=str))


if __name__ == "__main__":
    main()
