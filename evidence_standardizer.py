from source_ingestion_engine import normalize_source_record
from standard_evidence_builder import build_standard_evidence

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

    # If the connector that produced this record already set a real,
    # structured Evidence_Level (regulatory connectors like EMA/WHO/ESCOP
    # know this deterministically — it's not something that needs an LLM
    # to infer from free text), trust it and skip the LLM re-extraction
    # entirely for this record. Previously the LLM call below ran
    # unconditionally and OVERWROTE Evidence_Level with its own guess
    # from the Notes text — for regulatory records (short, structured
    # text the extraction prompt wasn't built for), that guess collapsed
    # to "Unknown" every time, silently discarding a correct value. This
    # applies to any connector that sets Evidence_Level up front, not
    # just EMA — e.g. it also protects the original curated
    # sleep-tea/REGULATORY_DB records, which had the same exposure.
    already_has_reliable_evidence_level = bool(
        record.get("Evidence_Level")
    )

    if extract_evidence_with_llm is not None and not already_has_reliable_evidence_level:
        try:
            llm = extract_evidence_with_llm(
                normalized,
                selected_dosage_form=normalized.get("Dosage_Form", ""),
                selected_indication=normalized.get("Target_Indication", ""),
            )

            normalized["Scientific_Name"] = llm.get(
                "plant_scientific_name",
                normalized.get("Scientific_Name", "")
            )

            normalized["Evidence_Type"] = llm.get("evidence_type", "")
            normalized["Study_Type"] = llm.get("evidence_type", "")
            normalized["Evidence_Level"] = llm.get("evidence_level", "")
            normalized["Study_Model"] = llm.get("study_model", "")

            normalized["Detected_Dosage_Forms"] = llm.get("dosage_form", "")
            normalized["Detected_Indications"] = llm.get("target_indication", "")
            normalized["Dosage_Form_Relevance"] = llm.get("dosage_form_relevance", "")

            normalized["LLM_Population"] = llm.get("population", "")
            normalized["LLM_Sample_Size"] = llm.get("sample_size", "")
            normalized["LLM_Comparator"] = llm.get("comparator", "")
            normalized["LLM_Main_Outcome"] = llm.get("main_outcome", "")
            normalized["LLM_Result_Direction"] = llm.get("result_direction", "")
            normalized["LLM_Safety_Signal"] = llm.get("safety_signal", "")
            normalized["LLM_Reason"] = llm.get("reason", "")

            if llm.get("ema_relevance", "").lower() == "yes":
                normalized["EMA_Status"] = "Yes"

            if llm.get("who_relevance", "").lower() == "yes":
                normalized["WHO_Status"] = "Yes"

            if llm.get("escop_relevance", "").lower() == "yes":
                normalized["ESCOP_Status"] = "Yes"

            if llm.get("safety_signal"):
                normalized["Safety_Signal"] = llm.get("safety_signal", "")

        except Exception as e:
            normalized["LLM_Reason"] = "LLM extraction failed: " + str(e)

    standardized = build_standard_evidence(normalized)

    return standardized
