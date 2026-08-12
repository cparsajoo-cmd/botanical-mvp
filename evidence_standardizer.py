import os
import json
from source_ingestion_engine import normalize_source_record
from standard_evidence_builder import build_standard_evidence
from standard_evidence_schema import canonicalize_evidence_record
from evidence_authority import classify_source_authority_from_row

try:
    from llm_extractor import extract_evidence_with_llm, extract_gate_assertions_with_llm
except Exception:
    extract_evidence_with_llm = None
    extract_gate_assertions_with_llm = None


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
        "Preparation", "Dose", "Requested_Dosage_Form", "Requested_Target_Indication",
        "Regulatory_Authorization_Status",
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

    # Canonical assertion activation: a reliable Evidence_Level answers
    # "what kind/strength of evidence is this?", not "what did it find?".
    # Previously, having Evidence_Level suppressed the LLM extraction entirely,
    # which meant the strongest systematic-review records often never received
    # Result_Direction/Safety_Signal and downstream code fell back to regex.
    # Run extraction whenever any core scientific assertion is still missing.
    # Direction is the mandatory canonical assertion for therapeutic
    # decision-making. Do not call the LLM merely because an optional
    # methodological/safety field is blank; that would turn every record into
    # an unnecessary model call. Safety extraction can still ride along when
    # a direction extraction is needed, while source-provided Safety_Signal is
    # always preserved.
    needs_structured_assertion = not normalized.get("Result_Direction")
    # Preparation transferability is a first-class scientific context, not a
    # presentation detail.  If any material study-context field is still
    # absent, let the structured extractor try to recover it from the source
    # text.  Missing values remain missing when the text does not support them.
    needs_transferability_context = any(
        not normalized.get(field)
        for field in ("Preparation", "Administration_Route", "Dose", "Plant_Part")
    )

    if extract_evidence_with_llm is not None and (
        not already_has_reliable_evidence_level
        or needs_structured_assertion
        or needs_transferability_context
    ):
        try:
            llm = extract_evidence_with_llm(
                normalized,
                selected_dosage_form=(
                    normalized.get("Requested_Dosage_Form") or normalized.get("Dosage_Form", "")
                ),
                selected_indication=(
                    normalized.get("Requested_Target_Indication") or normalized.get("Target_Indication", "")
                ),
            )

            if not normalized.get("Scientific_Name"):
                normalized["Scientific_Name"] = llm.get("plant_scientific_name", "")

            # Never overwrite reliable connector/source fields merely because
            # structured assertion extraction was needed.
            if not normalized.get("Evidence_Type"):
                normalized["Evidence_Type"] = llm.get("evidence_type", "")
            if not normalized.get("Study_Type"):
                normalized["Study_Type"] = llm.get("evidence_type", "")
            if not normalized.get("Evidence_Level"):
                normalized["Evidence_Level"] = llm.get("evidence_level", "")
            if not normalized.get("Study_Model"):
                normalized["Study_Model"] = llm.get("study_model", "")

            # Study preparation/context fields are extracted from the SOURCE
            # text, never from the selected product context.  Connector/source
            # values retain precedence; the LLM only fills genuinely missing
            # fields.  Provenance markers stay additive and are never consumed
            # as if they were source-provided values.
            _llm_transferability_filled = []
            for _field, _llm_key in (
                ("Plant_Part", "plant_part"),
                ("Preparation", "preparation"),
                ("Administration_Route", "administration_route"),
                ("Dose", "dose"),
                ("Extraction_Method", "extraction_method"),
                ("Duration", "duration"),
            ):
                if not normalized.get(_field) and llm.get(_llm_key):
                    normalized[_field] = llm.get(_llm_key, "")
                    _llm_transferability_filled.append(_field)
            if llm.get("preparation_category"):
                normalized["LLM_Preparation_Category"] = llm.get("preparation_category")
            if llm.get("dose_unit"):
                normalized["LLM_Dose_Unit"] = llm.get("dose_unit")
            if _llm_transferability_filled:
                normalized["Transferability_Extraction_Provenance"] = (
                    "llm_text_extraction:" + ",".join(_llm_transferability_filled)
                )

            if not normalized.get("Detected_Dosage_Forms"):
                normalized["Detected_Dosage_Forms"] = llm.get("dosage_form", "")
            if not normalized.get("Dosage_Form") and llm.get("dosage_form"):
                # Canonical STUDY dosage form. Requested_Dosage_Form is kept in
                # its own transient field and is never used as a fallback here.
                normalized["Dosage_Form"] = llm.get("dosage_form", "")
            if not normalized.get("Detected_Indications"):
                normalized["Detected_Indications"] = llm.get("target_indication", "")
            if not normalized.get("Target_Indication") and llm.get("target_indication"):
                # Canonical STUDY indication. This replaces the old collector
                # behavior that wrote the user's requested indication into the
                # evidence row even when the study investigated something else.
                normalized["Target_Indication"] = llm.get("target_indication", "")
            if not normalized.get("Dosage_Form_Relevance"):
                normalized["Dosage_Form_Relevance"] = llm.get("dosage_form_relevance", "")

            normalized["LLM_Population"] = llm.get("population", "")
            normalized["LLM_Sample_Size"] = llm.get("sample_size", "")
            normalized["LLM_Comparator"] = llm.get("comparator", "")
            normalized["LLM_Main_Outcome"] = llm.get("main_outcome", "")
            # Root-cause fix (2026-08-11, external audit point 4,
            # independently confirmed: test_canonical_assertion_
            # standardizer_activation.py explicitly asserted
            # out["Result_Direction"] == "Positive" from a fake_llm mock
            # with NO source-provided direction at all -- i.e. the test
            # had encoded this bug as expected behavior). LLM output must
            # ONLY ever land in the dedicated LLM_* columns -- the whole
            # point of adding those columns (see the canonical resolver's
            # source > llm_result_direction > reported_direction
            # precedence in canonical_scientific_assertion.py, and the
            # 2026-08-10 backfill_canonical_assertions.py incident where
            # the LLM's own output had been getting written into
            # result_direction) is that Result_Direction/Safety_Signal
            # must stay genuinely source-only so that precedence is
            # trustworthy. A model's inference must never be able to
            # masquerade as something the source directly reported, no
            # matter how confident the extraction. Previously this
            # function copied the LLM's result_direction/safety_signal
            # into Result_Direction/Safety_Signal whenever those were
            # still empty -- exactly the failure mode the dedicated
            # LLM_* columns exist to prevent.
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

        except Exception as e:
            normalized["LLM_Reason"] = "LLM extraction failed: " + str(e)
            # Root-cause fix (2026-08-11, same audit point as above): on
            # extraction failure this used to write the synthetic string
            # "Unknown" into the source-only Result_Direction field --
            # fabricating a value no source ever reported, in a field
            # whose entire purpose is to hold ONLY what the source
            # genuinely said. Leaving it unset lets the canonical
            # resolver's normal precedence (source > llm_result_direction
            # > reported_direction/text-fallback) apply correctly instead.

    # High-stakes semantic gate extraction is enabled by default for new
    # evidence.  It remains independently switchable for operational reasons,
    # but disabling/failing it does NOT make a record "clean": the decision
    # engine treats missing semantic coverage as EXPERT_REVIEW_REQUIRED when a
    # row would otherwise be eligible.  Raw source fields are never overwritten;
    # only the dedicated JSON assertion payload is added.
    _semantic_gate_enabled = str(os.getenv("ENABLE_SEMANTIC_GATE_EXTRACTION", "true")).strip().lower() in {
        "1", "true", "yes", "on"
    }
    if _semantic_gate_enabled and extract_gate_assertions_with_llm is not None:
        try:
            _gate_payload = extract_gate_assertions_with_llm(
                normalized,
                candidate_context=" | ".join(
                    str(x).strip() for x in (
                        normalized.get("Target_Indication", ""),
                        normalized.get("Dosage_Form", ""),
                        normalized.get("Target_Market", ""),
                    ) if str(x or "").strip()
                ),
            )
            normalized["LLM_Gate_Assertions"] = _gate_payload
        except Exception as e:
            # Failure is explicit and non-destructive.  Existing deterministic
            # gates still run; audit tooling can identify rows where semantic
            # extraction did not complete.
            normalized["LLM_Gate_Assertions_Error"] = str(e)

    # Scientific provenance invariant: Result_Direction is SOURCE-ONLY.
    # If the source did not explicitly provide a direction, leave it missing.
    # LLM inference belongs exclusively in LLM_Result_Direction.  Writing a
    # synthetic "Unknown" here would still make downstream provenance say
    # "source_result_direction", which is scientifically false even though the
    # value is conservative.  Missing source direction is represented by an
    # actually missing/empty source field and downstream resolution can then
    # distinguish source, LLM and legacy/text fallback correctly.

    standardized = build_standard_evidence(normalized)

    # PHASE 3 — Source Authority classification now actually runs at
    # standardization time (the same boundary that already computes
    # Study_Type/Result_Direction/Evidence_Level), using the single
    # shared classifier in evidence_authority.py so this pipeline and
    # candidate_shortlisting.py never diverge on how a source's authority
    # is determined. `Source_Authority_Weight` (the pre-Phase-3
    # connector-level float, still set by multi_source_collector.py from
    # source_registry.py) is left untouched here and continues to flow
    # through as backward-compatible passthrough metadata (see the
    # preserved-fields loop above) — it is a coarser, connector-only
    # signal and is superseded, not replaced in-place, by this
    # metadata-aware classification.
    #
    # Never overwrites a value the record already explicitly carries
    # (e.g. a test or an upstream step that already set Source_Authority)
    # — only fills it in when genuinely absent, consistent with this
    # module's "never guesses/never overwrites a reliable existing value"
    # pattern used above for Evidence_Level.
    if not standardized.get("Source_Authority"):
        authority = classify_source_authority_from_row(standardized)
        standardized["Source_Authority"] = authority.label
        standardized["Source_Authority_Score"] = authority.score
        standardized["Source_Authority_Reason"] = authority.reason

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
