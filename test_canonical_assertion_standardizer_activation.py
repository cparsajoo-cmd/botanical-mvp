
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
    # Root-cause fix (2026-08-11, external audit point 4): this test used
    # to assert out["Result_Direction"] == "Positive" -- i.e. it had
    # encoded the LLM's inferred direction leaking into the source-only
    # field as EXPECTED behavior. No source ever reported a direction
    # here (the input record has no Result_Direction at all); "Positive"
    # is purely the fake_llm mock's inference. The genuinely-source-only
    # Result_Direction must therefore stay empty/absent, while the model's
    # output belongs ONLY in LLM_Result_Direction/LLM_Safety_Signal.
    assert out.get("Result_Direction") in (None, ""), (
        "no source ever reported a direction here -- Result_Direction must not "
        "contain either the LLM inference or a synthetic source placeholder"
    )
    assert out["LLM_Result_Direction"] == "Positive"
    assert out.get("Safety_Signal") in (None, ""), (
        "no source ever reported a safety signal here -- Safety_Signal must not "
        "silently absorb the LLM's inference"
    )
    assert out["LLM_Safety_Signal"] == "No serious adverse events"


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


def test_new_standardized_record_without_extractor_does_not_fabricate_source_direction(monkeypatch):
    monkeypatch.setattr(es,"extract_evidence_with_llm",None)
    out=es.standardize_extracted_record(
        {
            "Scientific_Name":"Example plant",
            "Evidence_Level":"High",
            "Notes":"The intervention was more effective than placebo.",
            "Target_Indication":"pain",
            "Dosage_Form":"oral",
        },
        {"source_type":"PubMed","source_title":"x","source_url":"u","source_year":"2025"},
    )
    assert out.get("Result_Direction") in (None, "")


def test_semantic_gate_extraction_is_enabled_by_default_for_new_records(monkeypatch):
    monkeypatch.delenv("ENABLE_SEMANTIC_GATE_EXTRACTION", raising=False)
    monkeypatch.setattr(es, "extract_evidence_with_llm", None)
    calls = []

    def fake_gate(record, candidate_context=""):
        calls.append((record, candidate_context))
        return {"safety_assertions": [], "regulatory_assertions": []}

    monkeypatch.setattr(es, "extract_gate_assertions_with_llm", fake_gate)
    out = es.standardize_extracted_record(
        {
            "Scientific_Name": "Example plant",
            "Evidence_Level": "High",
            "Result_Direction": "Positive",
            "Notes": "A controlled study reported improvement.",
            "Target_Indication": "pain",
            "Dosage_Form": "oral",
        },
        {"source_type": "PubMed", "source_title": "x", "source_url": "u", "source_year": "2025"},
    )
    assert calls, "semantic safety/regulatory assessment should run by default for new evidence"
    assert out["LLM_Gate_Assertions"] == {"safety_assertions": [], "regulatory_assertions": []}
