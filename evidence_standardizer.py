from source_ingestion_engine import normalize_source_record
from standard_evidence_builder import build_standard_evidence
from standard_evidence_schema import canonicalize_evidence_record

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

    # `normalize_source_record` filters every record through
    # source_ingestion_engine.STANDARD_FIELDS, an allowlist of keys that
    # does NOT include "Evidence_Level" at all — so even before my
    # earlier fix (skip the LLM overwrite), the connector's
    # Evidence_Level was being silently dropped right here, before the
    # LLM step ever ran. Skipping the LLM alone wasn't enough: with
    # nothing else setting it, the field ended up completely absent,
    # which downstream code defaults to "Unknown" anyway — same visible
    # symptom, different exact cause. It has to be copied back in by
    # hand from the connector's original (pre-normalize) record.
    already_has_reliable_evidence_level = bool(
        record.get("Evidence_Level")
    )

    if already_has_reliable_evidence_level:
        normalized["Evidence_Level"] = record["Evidence_Level"]

    # Phase 2 (IMPLEMENTATION_PLAN.md) — normalize_source_record's
    # STANDARD_FIELDS allowlist (source_ingestion_engine.py) does not
    # include PMID/DOI/NCT_ID/Sample_Size either, for the same reason
    # Evidence_Level needed the hand-copy above: connectors that already
    # fetched these values (europepmc_connector.py, crossref_connector.py,
    # clinicaltrials_connector.py, evidence_collector.py's PubMed path)
    # would otherwise have them silently dropped here before storage.
    # Copied back only when the connector actually set a non-empty value —
    # never defaulted or guessed for a source that didn't provide one.
    # Preserve connector-provided scientific fields that the legacy
    # normalize_source_record allowlist does not yet carry.  Values are copied
    # only when actually present; missing facts remain missing.
    for _source_field in (
        "PMID", "DOI", "NCT_ID", "Sample_Size",
        "Primary_Outcome", "Result_Direction", "Safety_Signal",
        "Adverse_Events", "Interactions_Structured", "Effect_Size", "P_Value",
        "Administration_Route", "Plant_Part", "Extraction_Method", "Duration",
        "Mechanism", "Target", "Data_Quality_Score",
        # PHASE 2 audit finding (PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md
        # section 3c) — multi_source_collector._save_records_from_connector()
        # sets these three on `record` before calling this function, but
        # source_ingestion_engine.STANDARD_FIELDS never carried them, so
        # normalize_source_record() silently dropped them, same class of
        # bug already fixed above for Evidence_Level/PMID/DOI/etc. No
        # persistence column consumes these today (see database.py), so
        # this only stops the silent drop before storage; it does not by
        # itself add a new evidence_records column.
        "Source_Authority_Weight", "Source_Priority", "Source_Category",
    ):
        if record.get(_source_field) not in (None, "", [], {}):
            normalized[_source_field] = record[_source_field]

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

            # Phase 2C (regulatory single-source-of-truth cleanup) — an
            # LLM's subjective "does this text seem EMA-relevant?"
            # judgment must never become a regulatory conclusion
            # (EMA_Status). It becomes a text-mention annotation only,
            # same as evidence_extractor.py's keyword-based detector —
            # the ONE canonical source for whether a plant is actually
            # listed in EMA's HMPC inventory remains
            # ema_regulatory_connector.py, consumed via
            # botanical_rd_candidate_engine._market_status()/
            # _eu_regulatory_status().
            if llm.get("ema_relevance", "").lower() == "yes":
                normalized["Regulatory_Reference_Detected"] = True

            if llm.get("who_relevance", "").lower() == "yes":
                normalized["WHO_Status"] = "Yes"

            if llm.get("escop_relevance", "").lower() == "yes":
                normalized["ESCOP_Status"] = "Yes"

            if llm.get("safety_signal"):
                normalized["Safety_Signal"] = llm.get("safety_signal", "")

        except Exception as e:
            normalized["LLM_Reason"] = "LLM extraction failed: " + str(e)

    standardized = build_standard_evidence(normalized)

    # PHASE 2 (review round, issue 1) — every record this function
    # returns now genuinely passes through the canonical EvidenceRecord
    # adapter before reaching any caller. canonicalize_evidence_record()
    # round-trips through EvidenceRecord.from_legacy_dict()/
    # .to_legacy_dict(): field-name normalization, None-vs-missing
    # discipline, and first_author derivation all actually run here in
    # production, not merely in a test that calls the adapter directly.
    # Return shape is unchanged (still a legacy-compatible dict) — no
    # caller of standardize_extracted_record() needs to change.
    return canonicalize_evidence_record(standardized)
