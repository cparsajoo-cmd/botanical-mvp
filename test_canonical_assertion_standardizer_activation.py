
import evidence_standardizer as es

def test_reliable_evidence_level_does_not_suppress_structured_assertion_extraction(monkeypatch):
    calls=[]
    def fake_llm(record, selected_dosage_form="", selected_indication=""):
        calls.append(record)
        return {
            "plant_scientific_name":"Example plant",
            "evidence_type":"Systematic Review",
            "study_model":"Human",
            "dosage_form":"oral",
            "target_indication":"pain",
            "dosage_form_relevance":"Direct",
            "population":"adults",
            "sample_size":"",
            "comparator":"placebo",
            "main_outcome":"pain",
            "result_direction":"Positive",
            "safety_signal":"No serious adverse events",
            "evidence_level":"Low",
            "ema_relevance":"No","who_relevance":"No","escop_relevance":"No",
            "reason":"structured extraction",
        }
    monkeypatch.setattr(es,"extract_evidence_with_llm",fake_llm)
    out=es.standardize_extracted_record(
        {
            "Scientific_Name":"Example plant",
            "Evidence_Level":"High",
            "Notes":"Review reported benefit.",
            "Target_Indication":"pain",
            "Dosage_Form":"oral",
        },
        {"source_type":"PubMed","source_title":"x","source_url":"u","source_year":"2025"},
    )
    assert calls, "LLM assertion extraction must run even when Evidence_Level is already reliable"
    assert out["Evidence_Level"] == "High", "source Evidence_Level must not be overwritten"
    assert out["Result_Direction"] == "Positive"
    assert out["Safety_Signal"] == "No serious adverse events"


def test_source_result_direction_prevents_unnecessary_llm_call(monkeypatch):
    def fail_llm(*args, **kwargs):
        raise AssertionError("LLM should not run when source Result_Direction is already present")
    monkeypatch.setattr(es,"extract_evidence_with_llm",fail_llm)
    out=es.standardize_extracted_record(
        {
            "Scientific_Name":"Example plant",
            "Evidence_Level":"High",
            "Result_Direction":"Positive",
            "Notes":"Connector already supplied a structured result direction.",
            "Target_Indication":"pain",
            "Dosage_Form":"oral",
        },
        {"source_type":"PubMed","source_title":"x","source_url":"u","source_year":"2025"},
    )
    assert out["Result_Direction"] == "Positive"
