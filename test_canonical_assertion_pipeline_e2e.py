
import pandas as pd
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from end_to_end_validation import _build_plant_df, _norm_taxon
from final_decision_policy import final_status_from_engine_row, FinalDecisionStatus

def _run(records, plant="Testus botanica", indication="test indication"):
    ev=pd.DataFrame(records)
    eng=BotanicalRDCandidateEngine(
        plant_compounds_df=_build_plant_df([plant],indication),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=ev,
        use_live_search=False,
    )
    out=eng.run(indication=indication,dosage_form="oral",market="EU")
    return out[out["Alternative_Plant"].map(_norm_taxon)==_norm_taxon(plant)].iloc[0]

def _base(rid, notes):
    return {
        "Evidence_Record_ID":rid,"Scientific_Name":"Testus botanica",
        "Target_Indication":"test indication","Dosage_Form":"oral","Target_Market":"EU",
        "Notes":notes,"Source_Type":"SYSTEMATIC_REVIEW",
        "Study_Type":"Systematic Review and Meta-analysis","Evidence_Level":"high",
        "Source_Year":2025,"Primary_Outcome":"test indication",
        "Comparator":"placebo","Risk_of_Bias":"assessed",
    }

def test_final_decision_consumes_structured_result_direction_authoritatively():
    a=_base("a","Wording intentionally contains no legacy efficacy keyword.")
    b=_base("b","Second wording also intentionally opaque to the text classifier.")
    a["Result_Direction"]="Positive"; b["Result_Direction"]="Positive"
    row=_run([a,b])
    assert final_status_from_engine_row(row) == FinalDecisionStatus.GO

def test_structured_safety_signal_reaches_hard_safety_path():
    a=_base("a","Clinical review record.")
    a["Result_Direction"]="Positive"
    a["Safety_Signal"]="Severe neurotoxicity with seizures and coma has been reported."
    row=_run([a])
    assert final_status_from_engine_row(row) == FinalDecisionStatus.NO_GO_SAFETY

def test_structured_regulatory_status_reaches_regulatory_gate():
    a=_base("a","Regulatory evidence record.")
    a["Result_Direction"]="Unknown"
    a["Source_Type"]="REGULATORY"
    a["Regulatory_Status"]="prohibited"
    a["Regulatory_Evidence"]="This botanical is prohibited from use in food supplements."
    row=_run([a],indication="use as a food supplement ingredient")
    assert final_status_from_engine_row(row) == FinalDecisionStatus.NO_GO_REGULATORY
