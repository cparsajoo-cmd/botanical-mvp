from source_ingestion_engine import normalize_source_record
from evidence_classifier import classify_evidence

try:
    from llm_extractor import extract_evidence_with_llm
except Exception:
    extract_evidence_with_llm = None


def standardize_extracted_record(extracted, source_metadata):
    record = extracted.copy()

    record["Source_Type"] = source_metadata.get("source_type", record.get("Source_Type", ""))
    record["Source_Title"] = source_metadata.get("source_title", record.get("Source_Title", ""))
    record["Source_URL"] = source_metadata.get("source_url", record.get("Source_URL", ""))
    record["Source_Organization"] = source_metadata.get(
        "source_organization",
        record.get("Source_Organization", "")
    )
    record["Source_Year"] = source_metadata.get("source_year", record.get("Source_Year", ""))

    normalized = normalize_source_record(record)

    if extract_evidence_with_llm is not None:
        try:
            llm = extract_evidence_with_llm(
                normalized,
                selected_dosage_form=normalized.get("Dosage_Form", ""),
                selected_indication=normalized.get("Target_Indication", "")
            )

            normalized["Scientific_Name"] = llm.get("plant_scientific_name", normalized.get("Scientific_Name", ""))
            normalized["Evidence_Type"] = llm.get("evidence_type", "")
            normalized["Evidence_Level"] = llm.get("evidence_level", "")
            normalized["Study_Model"] = llm.get("study_model", "")
            normalized["Detected_Dosage_Forms"] = llm.get("dosage_form", "")
            normalized["Detected_Indications"] = llm.get("target_indication", "")
            normalized["Dosage_Form_Relevance"] = llm.get("dosage_form_relevance", "")
            normalized["LLM_Population"] = llm.get("population", "")
            normalized["LLM_Comparator"] = llm.get("comparator", "")
            normalized["LLM_Main_Outcome"] = llm.get("main_outcome", "")
            normalized["LLM_Safety_Signal"] = llm.get("safety_signal", "")
            normalized["LLM_Reason"] = llm.get("reason", "")

        except Exception as e:
            normalized["LLM_Reason"] = "LLM extraction failed: " + str(e)

    classified = classify_evidence(normalized)

    return classified
