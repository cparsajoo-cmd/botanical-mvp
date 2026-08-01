import pandas as pd
from supabase_client import get_supabase_client

# ======================================================================
# Task 10.2 — REQUIRED SUPABASE SCHEMA CHANGE (not performed by this
# repository; no migration mechanism exists for any table here — see
# ARCHITECTURE.md's "Known oddities" and telemetry_persistence.py's/
# decision_record_persistence.py's identical precedent).
#
# save_evidence_record() below now writes, and load_evidence_records()
# now reads, five additional TEXT columns on the existing evidence_records
# table, plus reads (never writes) the table's own existing primary key:
#
#   applicability_classification         TEXT
#   applicability_rationale              TEXT
#   applicability_evaluated_dimensions   TEXT
#   applicability_missing_dimensions     TEXT
#   applicability_detected_mismatches    TEXT
#   id                                   (already exists as the table's
#                                          primary key — only newly READ
#                                          here, not newly written)
#
# DEPLOYMENT STATUS — read this before deploying, stated explicitly,
# not just implied:
#
#   1. READS degrade safely when the new columns are absent or the
#      values are null. load_evidence_records()'s item.get(<new key>, "")
#      returns "" for a column PostgREST's response doesn't contain at
#      all (unmigrated table) and for a column that exists but is NULL
#      on an old row (migrated table, pre-Task-10.2 row) — both cases
#      behave identically to every caller. No existing caller needs to
#      change to tolerate either case.
#
#   2. WRITES prefer all five columns when they exist. Against an older
#      table, save_evidence_record() detects PostgREST PGRST204 missing-
#      column errors and retries after removing only the unavailable
#      optional applicability fields. Core evidence fields remain strict.
#
#   3. This makes evidence collection backward-compatible with an
#      unmigrated production table while preserving the richer fields
#      automatically once the columns are added.
# ======================================================================




# ======================================================================
# IMPLEMENTATION_PLAN.md Phase 2 — additive evidence_records extension.
# See migrations/0002_extend_evidence_records.sql for the SQL (run by
# hand — same no-migration-runner situation as Task 10.2 above).
#
# save_evidence_record() now writes 14 additional nullable columns:
#   pmid, doi, nct_id                          TEXT  — identifiers the
#     PubMed / Europe PMC / CrossRef / ClinicalTrials.gov connectors
#     already fetch but previously discarded before persistence (see
#     each connector file's own comment at its PMID/DOI/NCT_ID line).
#   mechanism, target, administration_route,
#   plant_part, extraction_method, duration    TEXT  — schema-ready,
#     NOT populated by any connector in Phase 2 (none currently extracts
#     these reliably without risking inference/fabrication — left null).
#   effect_size, p_value,
#   adverse_events, interactions_structured    JSONB — same as above;
#     JSONB (not a bare number) because e.g. an effect size without its
#     type/unit/CI/timepoint is not scientifically meaningful on its own.
#   data_quality_score                         NUMERIC — schema-ready,
#     not populated in Phase 2 (a composite score is a scoring-engine
#     decision, out of Phase 2's scope).
#
# All 14 follow the SAME optional-column fallback as the five Task 10.2
# fields below — added to _OPTIONAL_EVIDENCE_COLUMNS, not a new mechanism.
# ======================================================================


_OPTIONAL_EVIDENCE_COLUMNS = {
    "applicability_classification",
    "applicability_rationale",
    "applicability_evaluated_dimensions",
    "applicability_missing_dimensions",
    "applicability_detected_mismatches",
    # Phase 2
    "pmid", "doi", "nct_id",
    "mechanism", "target", "administration_route",
    "plant_part", "extraction_method", "duration",
    "effect_size", "p_value", "adverse_events", "interactions_structured",
    "safety_findings", "data_quality_score",
}


def _missing_postgrest_column(exc):
    """Extract a missing column name from a PostgREST PGRST204 error."""
    text = str(exc)
    if "PGRST204" not in text and "schema cache" not in text:
        return None

    import re

    match = re.search(r"Could not find the ['\"]([^'\"]+)['\"] column", text)
    return match.group(1) if match else None


def _insert_evidence_with_optional_schema_fallback(supabase, payload):
    """Insert an evidence row while tolerating an older Supabase schema.

    The five Task-10.2 applicability fields are valuable when present, but
    older deployments may not yet have those columns. PostgREST rejects the
    whole row when any one field is unknown, so we retry after removing only
    the missing optional applicability field. All legacy/core evidence fields
    remain mandatory and continue to raise on schema errors.
    """
    current = dict(payload)
    removed = []

    for _ in range(len(_OPTIONAL_EVIDENCE_COLUMNS) + 1):
        try:
            result = supabase.table("evidence_records").insert(current).execute()
            if removed:
                print(
                    "[database] evidence_records schema is missing optional "
                    f"columns; saved without: {', '.join(removed)}"
                )
            return result
        except Exception as exc:
            missing = _missing_postgrest_column(exc)
            if missing not in _OPTIONAL_EVIDENCE_COLUMNS or missing not in current:
                raise
            current.pop(missing, None)
            removed.append(missing)

    raise RuntimeError("Unable to insert evidence record after schema fallback")


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _find_existing_source(supabase, url, title):
    if url:
        res = supabase.table("sources").select("id").eq("url", url).limit(1).execute()
        if res.data:
            return res.data[0]["id"]

    if title:
        res = supabase.table("sources").select("id").eq("title", title).limit(1).execute()
        if res.data:
            return res.data[0]["id"]

    return None


def _get_or_create_plant(supabase, scientific_name, common_name):
    scientific_name = scientific_name or ""

    if scientific_name:
        res = supabase.table("plants").select("id").eq("scientific_name", scientific_name).limit(1).execute()
        if res.data:
            return res.data[0]["id"]

    plant_result = supabase.table("plants").insert({
        "scientific_name": scientific_name,
        "common_name": common_name or "",
    }).execute()

    return plant_result.data[0]["id"]


def save_evidence_record(record):
    supabase = get_supabase_client()

    source_url = record.get("Source_URL", "")
    source_title = record.get("Source_Title", "")

    existing_source_id = _find_existing_source(
        supabase=supabase,
        url=source_url,
        title=source_title,
    )

    # Architectural correctness fix (post-Phase-2 review): plant_id must be
    # resolved BEFORE the duplicate-evidence lookup, and included in it.
    # Two different plants can legitimately share the same source article,
    # indication, and dosage form (e.g. one review article covering both
    # Morus alba and Trigonella foenum-graecum for type 2 diabetes, oral
    # dosage form) — without plant_id in the lookup, the second plant's
    # evidence record was incorrectly treated as a duplicate of the
    # first's and silently dropped. This is unacceptable in an
    # evidence-centric system: candidate entry now depends entirely on
    # each plant HAVING its own evidence, so losing one plant's row to a
    # false-duplicate match would silently remove it from consideration.
    plant_id = _get_or_create_plant(
        supabase=supabase,
        scientific_name=record.get("Scientific_Name", ""),
        common_name=record.get("Common_Name", ""),
    )

    if existing_source_id:
        existing_evidence = (
            supabase.table("evidence_records")
            .select("id")
            .eq("plant_id", plant_id)
            .eq("source_id", existing_source_id)
            .eq("target_indication", record.get("Target_Indication", ""))
            .eq("dosage_form", record.get("Dosage_Form", ""))
            .limit(1)
            .execute()
        )

        if existing_evidence.data:
            return existing_evidence.data[0]["id"]

    if existing_source_id:
        source_id = existing_source_id
    else:
        source_result = supabase.table("sources").insert({
            "source_type": record.get("Source_Type", ""),
            "organization": record.get("Source_Organization", ""),
            "title": source_title,
            "year": record.get("Source_Year", ""),
            "url": source_url,
            "raw_text": record.get("Notes", ""),
        }).execute()
        source_id = source_result.data[0]["id"]

    evidence_payload = {
        "plant_id": plant_id,
        "source_id": source_id,

        "product_type": record.get("Product_Type", ""),
        "dosage_form": record.get("Dosage_Form", ""),
        "target_indication": record.get("Target_Indication", ""),
        "target_market": record.get("Target_Market", ""),

        "ema_status": record.get("EMA_Status", ""),
        "who_status": record.get("WHO_Status", ""),
        "escop_status": record.get("ESCOP_Status", ""),

        "clinical_level": record.get("Clinical_Level", ""),
        "clinical_rct_count": _safe_int(record.get("Clinical_RCT_Count", 0)),
        "meta_level": record.get("Meta_Level", ""),
        "meta_count": _safe_int(record.get("Meta_Count", 0)),

        "dosage_form_evidence": record.get("Dosage_Form_Evidence", record.get("Infusion_Evidence", "")),
        "safety_level": record.get("Safety_Level", ""),
        "drug_interaction_level": record.get("Drug_Interaction_Level", ""),
        "commercial_level": record.get("Commercial_Level", ""),
        "regulatory_status": record.get("Regulatory_Status", ""),
        "novel_food_status": record.get("Novel_Food_Status", ""),
        "notes": record.get("Notes", ""),

        "evidence_type": record.get("Evidence_Type", ""),
        "evidence_level": record.get("Evidence_Level", ""),
        "dosage_form_relevance": record.get("Dosage_Form_Relevance", ""),
        "study_model": record.get("Study_Model", ""),
        "detected_dosage_forms": record.get("Detected_Dosage_Forms", ""),
        "detected_indications": record.get("Detected_Indications", ""),
        "regulatory_evidence": record.get("Regulatory_Evidence", ""),
        "evidence_score": _safe_int(record.get("Evidence_Score", 0)),

        "plant": record.get("Plant", ""),
        "study_type": record.get("Study_Type", ""),
        "dosage_form_detected": record.get("Dosage_Form_Detected", ""),
        "target_indication_detected": record.get("Target_Indication_Detected", ""),
        "population": record.get("Population", ""),
        "sample_size": record.get("Sample_Size", ""),
        "comparator": record.get("Comparator", ""),
        "primary_outcome": record.get("Primary_Outcome", ""),
        "result_direction": record.get("Result_Direction", ""),
        "safety_signal": record.get("Safety_Signal", ""),
        "direct_for_selected_product": record.get("Direct_For_Selected_Product", ""),
        "directness_reason": record.get("Directness_Reason", ""),

        # Task 10.2 — Evidence-level Preparation Applicability. Additive
        # only; never overwrites/duplicates direct_for_selected_product/
        # directness_reason above. REQUIRES these five columns to exist
        # on the real Supabase evidence_records table before this will
        # persist anything — see REQUIRED_SUPABASE_COLUMNS_TASK_10_2 at
        # the top of this module. Like every other table in this
        # repository, there is no migration file; until the columns are
        # added by hand in Supabase, this insert raises a PostgREST
        # "column does not exist" error, exactly like adding any other
        # new column to this dict would. save_evidence_record() itself
        # has never caught its own exceptions (true before this task
        # too — every field in this insert shares this risk). Whether a
        # caller sees that raised exception or a graceful per-record
        # error depends on the caller: multi_source_collector.py's
        # _save_records_from_connector() wraps this call in a per-record
        # try/except and reports failures in its `errors` list (the
        # dominant, Step-2 production path); evidence_collector.py's
        # collect_pubmed_evidence() and source_pipeline.py's
        # run_source_pipeline() do not wrap this call and would
        # propagate the exception. This is pre-existing behavior,
        # unchanged by this task.
        "applicability_classification": record.get("Applicability_Classification", ""),
        "applicability_rationale": record.get("Applicability_Rationale", ""),
        "applicability_evaluated_dimensions": record.get("Applicability_Evaluated_Dimensions", ""),
        "applicability_missing_dimensions": record.get("Applicability_Missing_Dimensions", ""),
        "applicability_detected_mismatches": record.get("Applicability_Detected_Mismatches", ""),

        # Phase 2 (IMPLEMENTATION_PLAN.md). Deliberately `.get(key) or None`,
        # not `.get(key, "")` like the legacy TEXT fields above: an empty
        # string would misrepresent "we have no value" as "the value is the
        # empty string" for these newer, more structured fields. None here
        # means exactly one thing — this connector/record did not provide
        # this field — never an inferred or guessed value.
        "pmid": record.get("PMID") or None,
        "doi": record.get("DOI") or None,
        "nct_id": record.get("NCT_ID") or None,
        "mechanism": record.get("Mechanism") or None,
        "target": record.get("Target") or None,
        "administration_route": record.get("Administration_Route") or None,
        "plant_part": record.get("Plant_Part") or None,
        "extraction_method": record.get("Extraction_Method") or None,
        "duration": record.get("Duration") or None,
        "effect_size": record.get("Effect_Size") or None,
        "p_value": record.get("P_Value") or None,
        "adverse_events": record.get("Adverse_Events") or None,
        "interactions_structured": record.get("Interactions_Structured") or None,
        "safety_findings": record.get("Safety_Findings") or record.get("Safety_Findings_Raw") or None,
        "data_quality_score": record.get("Data_Quality_Score") or None,
    }

    evidence_result = _insert_evidence_with_optional_schema_fallback(
        supabase, evidence_payload
    )

    return evidence_result.data[0]["id"]


def get_evidence_record_count():
    """Total row count in evidence_records, without fetching row bodies.

    Uses PostgREST's exact count (returned in the response metadata
    regardless of how many rows are actually returned) combined with
    range(0, 0) so at most one row's data crosses the wire. This lets
    the UI show "N total records" without paying for a full-table fetch
    just to find out N.
    """
    supabase = get_supabase_client()
    response = (
        supabase.table("evidence_records")
        .select("id", count="exact")
        .range(0, 0)
        .execute()
    )
    return response.count if response.count is not None else 0


def load_evidence_records():
    supabase = get_supabase_client()

    response = supabase.table("evidence_records").select(
        "*, plants(scientific_name, common_name), sources(*)"
    ).execute()

    rows = []

    for item in response.data:
        plant = item.get("plants") or {}
        source = item.get("sources") or {}

        rows.append({
            "Plant_ID": item.get("plant_id", ""),
            "Scientific_Name": plant.get("scientific_name", ""),
            "Common_Name": plant.get("common_name", ""),

            "Product_Type": item.get("product_type", ""),
            "Dosage_Form": item.get("dosage_form", ""),
            "Target_Indication": item.get("target_indication", ""),
            "Target_Market": item.get("target_market", ""),

            "EMA_Status": item.get("ema_status", ""),
            "WHO_Status": item.get("who_status", ""),
            "ESCOP_Status": item.get("escop_status", ""),

            "Clinical_Level": item.get("clinical_level", ""),
            "Clinical_RCT_Count": item.get("clinical_rct_count", 0),
            "Meta_Level": item.get("meta_level", ""),
            "Meta_Count": item.get("meta_count", 0),

            "Dosage_Form_Evidence": item.get("dosage_form_evidence", ""),
            "Infusion_Evidence": item.get("dosage_form_evidence", ""),

            "Safety_Level": item.get("safety_level", ""),
            "Drug_Interaction_Level": item.get("drug_interaction_level", ""),
            "Commercial_Level": item.get("commercial_level", ""),
            "Regulatory_Status": item.get("regulatory_status", ""),
            "Novel_Food_Status": item.get("novel_food_status", ""),
            "Notes": item.get("notes", ""),

            "Evidence_Type": item.get("evidence_type", ""),
            "Evidence_Level": item.get("evidence_level", ""),
            "Dosage_Form_Relevance": item.get("dosage_form_relevance", ""),
            "Study_Model": item.get("study_model", ""),
            "Detected_Dosage_Forms": item.get("detected_dosage_forms", ""),
            "Detected_Indications": item.get("detected_indications", ""),
            "Regulatory_Evidence": item.get("regulatory_evidence", ""),
            "Evidence_Score": item.get("evidence_score", 0),

            "Plant": item.get("plant", ""),
            "Study_Type": item.get("study_type", ""),
            "Dosage_Form_Detected": item.get("dosage_form_detected", ""),
            "Target_Indication_Detected": item.get("target_indication_detected", ""),
            "Population": item.get("population", ""),
            "Sample_Size": item.get("sample_size", ""),
            "Comparator": item.get("comparator", ""),
            "Primary_Outcome": item.get("primary_outcome", ""),
            "Result_Direction": item.get("result_direction", ""),
            "Safety_Signal": item.get("safety_signal", ""),
            "Direct_For_Selected_Product": item.get("direct_for_selected_product", ""),
            "Directness_Reason": item.get("directness_reason", ""),

            # Task 10.2. .get(..., "") on a column that does not exist
            # yet on the real Supabase table simply returns "" (item is
            # a plain dict from PostgREST's response — a missing key
            # behaves exactly like an existing-but-null one), so old
            # rows / a not-yet-migrated table degrade to "" here rather
            # than raising — no caller needs to change to tolerate the
            # column's absence.
            "Applicability_Classification": item.get("applicability_classification", ""),
            "Applicability_Rationale": item.get("applicability_rationale", ""),
            "Applicability_Evaluated_Dimensions": item.get("applicability_evaluated_dimensions", ""),
            "Applicability_Missing_Dimensions": item.get("applicability_missing_dimensions", ""),
            "Applicability_Detected_Mismatches": item.get("applicability_detected_mismatches", ""),

            # Phase 2 (IMPLEMENTATION_PLAN.md). item.get(<new key>) returns
            # None both when the column doesn't exist yet (unmigrated
            # table) and when it exists but is genuinely null — same
            # degrade-safely behavior as the Task 10.2 fields above, kept
            # as None (not "") on the way out too, so a caller can tell
            # "no value was ever recorded" apart from "recorded as empty".
            "PMID": item.get("pmid"),
            "DOI": item.get("doi"),
            "NCT_ID": item.get("nct_id"),
            "Mechanism": item.get("mechanism"),
            "Target": item.get("target"),
            "Administration_Route": item.get("administration_route"),
            "Plant_Part": item.get("plant_part"),
            "Extraction_Method": item.get("extraction_method"),
            "Duration": item.get("duration"),
            "Effect_Size": item.get("effect_size"),
            "P_Value": item.get("p_value"),
            "Adverse_Events": item.get("adverse_events"),
            "Interactions_Structured": item.get("interactions_structured"),
            "Safety_Findings": item.get("safety_findings"),
            "Data_Quality_Score": item.get("data_quality_score"),

            # Task 10.2 — previously discarded on read (id was selected
            # implicitly via "*" but never mapped into the returned row
            # dict). Needed so a candidate's Applicability_Summary can
            # cite the exact evidence_records row(s) it was built from,
            # not just a plant/compound name (rule: "Do not claim
            # traceability merely through plant or compound names").
            "Evidence_Record_ID": item.get("id", ""),

            "Reference_Count": 1,
            "Source_Type": source.get("source_type", ""),
            "Source_Title": source.get("title", ""),
            "Source_Organization": source.get("organization", ""),
            "Source_Year": source.get("year", ""),
            "Source_URL": source.get("url", ""),
        })

    return pd.DataFrame(rows)
