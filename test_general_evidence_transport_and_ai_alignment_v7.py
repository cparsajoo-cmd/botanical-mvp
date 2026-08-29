import pandas as pd

import indication_candidate_discovery as icd
import candidate_shortlisting as cs
import evidence_adjudication_engine as eae
import step_rd_candidates as srd


class _Engine:
    def __init__(self, evidence_records, candidates):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame(evidence_records)
        self._candidates = pd.DataFrame(candidates)

    def _candidate_frame(self):
        return self._candidates

    def _pick(self, row, names):
        for name in names:
            try:
                value = row.get(name, "")
            except AttributeError:
                value = ""
            if value is not None and str(value).strip() and str(value).lower() not in {"nan", "none", "null"}:
                return str(value).strip()
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        low = str(text).lower()
        return "Clinical / human evidence" if any(x in low for x in ("human", "randomized", "clinical trial")) else "Unknown"


def test_discovery_transports_source_outcome_and_study_context_generically():
    indication = "zorvanic discomfort"
    engine = _Engine(
        [{
            "Scientific_Name": "Fictus alpha",
            "Evidence_Record_ID": "E-1",
            "Target_Indication": indication,
            "Study_Type": "Randomized placebo-controlled clinical trial",
            "Study_Model": "Human",
            "Population": "Adults",
            "Primary_Outcome": f"Improved {indication} symptom score",
            "Result_Direction": "positive",
            "Title": f"Clinical trial of Fictus alpha for {indication}",
            "Abstract": f"Treatment improved {indication} compared with placebo.",
        }],
        [{"Scientific_Name": "Fictus alpha", "Known_Active_Compounds": "x", "Known_Targets": "y", "Indications_Text": ""}],
    )
    raw = icd.discover_indication_candidates(engine, indication, dosage_form="oral")
    assert not raw.empty
    row = raw.iloc[0]
    assert row["Primary_Outcome"]
    assert row["Study_Type"]
    assert row["Study_Model"]
    assert row["Population"]
    assert indication in str(row["Source_Outcome_Text"]).lower()
    assert indication in str(row["Source_Evidence_Text"]).lower()


def test_primary_direct_count_no_longer_depends_on_optional_structured_outcome():
    indication = "zorvanic discomfort"
    raw = pd.DataFrame([{
        "Alternative_Plant": "Fictus alpha",
        "Reference_Plant": "Indication-centric discovery",
        "Source_Record_IDs": "E-1",
        "Evidence_Source": "PubMed",
        "Indication_Match_Type": "exact_indication",
        "Indication_Match_Terms": indication,
        "Indication_Match_Reason": "Exact indication phrase matched in source text (title/abstract/notes)",
        "Evidence_Level": "Human clinical trial",
        "Evidence_Hierarchy_Detail": "Clinical trial",
        "Study_Type": "Randomized placebo-controlled clinical trial",
        "Study_Model": "Human",
        "Population": "Adults",
        # No Primary_Outcome: this is deliberately a connector with only source text.
        "Primary_Outcome": "",
        "Source_Outcome_Text": "",
        "Source_Evidence_Text": f"Randomized clinical trial for {indication}",
        "Result_Direction": "unknown",
        "Scientific_Rationale": "human clinical trial",
        "Clinical_Rationale": "clinical evidence",
        "Target_or_Mechanism": "",
        "R&D_Opportunity_Score": 50,
        "Decision_Class_AH": "C",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Eligible_For_Normal_Ranking": True,
        "Eligibility_Status": "eligible",
        "Hard_No_Go": False,
        "Dosage_Form_Compatibility": "Compatible",
        "Safety_Flags": "",
        "Interaction_Flags": "",
    }])
    summary, audit = cs.build_plant_candidate_shortlist(raw, indication=indication, dosage_form="oral")
    row = summary.iloc[0]
    assert row["Indication_Evidence_Mode"] == "Direct human/clinical"
    assert row["Direct_Indication_Evidence_Count"] == 1
    # Outcome-specific is intentionally stricter than direct indication relevance.
    assert row["Outcome_Specific_Direct_Evidence_Count"] == 0
    assert row["Outcome_Specific_Human_Evidence_Count"] == 0
    assert bool(audit.iloc[0]["Outcome_Specific_Direct_Evidence"]) is False


def test_adjacent_outcome_does_not_become_outcome_specific_from_explicit_indication_alone():
    indication = "zorvanic discomfort"
    row = pd.Series({
        "Source_Explicit_Indication_Text": indication,
        "Primary_Outcome": "exercise fatigue and recovery",
        "Source_Outcome_Text": "exercise fatigue and recovery",
        "Source_Evidence_Text": f"Study population with {indication}; primary endpoint was exercise fatigue",
        "Result_Direction": "unknown",
    })
    assert cs._row_has_indication_specific_outcome(row, indication) is False


def test_processed_stage5_audit_is_the_single_ai_evidence_source():
    raw = pd.DataFrame([{"Alternative_Plant": "Fictus alpha", "Source_Record_IDs": "RAW"}])
    audit = pd.DataFrame([{
        "Alternative_Plant": "Fictus alpha",
        "Source_Record_IDs": "AUDIT",
        "Canonical_Study_Context": "HUMAN",
        "Outcome_Specific_Direct_Evidence": True,
        "Outcome_Specific_Human_Evidence": True,
    }])
    selected = srd._authoritative_ai_evidence_df(raw, audit)
    assert selected is audit
    assert selected.iloc[0]["Source_Record_IDs"] == "AUDIT"
    assert srd._authoritative_ai_evidence_df(raw, pd.DataFrame()) is raw


def test_adjudication_consumes_transported_source_text_and_canonical_context():
    indication = "zorvanic discomfort"
    audit = pd.DataFrame([{
        "Alternative_Plant": "Fictus alpha",
        "Source_Record_IDs": "E-1",
        "Indication_Match_Type": "exact_indication",
        "Indication_Match_Reason": "Exact indication phrase matched the record's own reported outcome",
        "Canonical_Study_Context": "HUMAN",
        "Outcome_Specific_Direct_Evidence": True,
        "Outcome_Specific_Human_Evidence": True,
        "Source_Outcome_Text": f"Improved {indication}",
        "Source_Evidence_Text": f"Randomized trial: treatment improved {indication} versus placebo.",
        "Result_Direction": "positive",
        "Study_Type": "Randomized placebo-controlled clinical trial",
    }])
    items = eae.build_adjudication_evidence_items(audit, "Fictus alpha", indication)
    assert len(items) == 1
    item = items[0]
    assert item["human_animal_in_vitro"] == "HUMAN"
    assert item["outcome_specific"] is True
    assert indication in (item["evidence_text_snippet"] or "").lower()
