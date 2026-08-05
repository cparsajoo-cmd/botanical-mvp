import pandas as pd
from supabase_client import get_supabase_client
from standard_evidence_schema import canonicalize_evidence_record
from deduplication_engine import (
    normalize_doi,
    normalize_pmid,
    normalize_trial_registration,
    articles_equivalent,
    evidence_contexts_equivalent,
    get_first_present,
)

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
    # PHASE 2 (review round 5) — migrations/0006_add_dose_preparation.sql.
    # See that file's header for why these are two separate columns, and
    # why "preparation" is never conflated with "extraction_method".
    "dose", "preparation",
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


def _fetch_evidence_identity_candidates(supabase, plant_id, indication, dosage_form,
                                         id_field, id_value):
    """PHASE 2 (review round 3, issue 1 fix; review round 5, dose/
    preparation fix) — fetches every existing evidence_records row that
    shares the same plant_id/indication/dosage_form AND the same strong
    identifier (doi/pmid/nct_id, or a matched source_id) as the new
    record, WITH the fields needed to compute a real
    evidence_contexts_equivalent() comparison (not just the row id).

    This replaces the old single .limit(1) lookup, which stopped at
    "same DOI + same plant/indication/dosage_form" and silently treated
    that as a duplicate — collapsing genuinely different Evidence
    (different outcome, direction, population, dose, preparation, etc.)
    from the same article. Now the caller must additionally confirm an
    evidence_contexts_equivalent() match on one of the returned
    candidates before treating anything as a duplicate.

    Returns:
      - a list of candidate row dicts (possibly empty — no candidates
        found at all, which is a normal, non-ambiguous "no duplicate
        possible" result)
      - None if the query could not be resolved at all (e.g. the
        doi/pmid/nct_id column itself doesn't exist on this deployment)
        — the caller MUST treat None as "cannot determine, therefore
        not a duplicate" (never silently collapse on missing data).

    plant_part/dose/preparation are fetched when available but are
    OPTIONAL columns (_OPTIONAL_EVIDENCE_COLUMNS; dose/preparation added
    by migrations/0006_add_dose_preparation.sql). On an older deployment
    missing one or more of them, this retries with progressively fewer
    optional columns (never a query that removes a REQUIRED column, and
    never silently reinterpreted as "not found" — a missing optional
    column just means that one dimension always compares as "" on both
    sides for that deployment; the other, always-present dimensions —
    outcome, direction, population, study_type, notes — still fully gate
    the comparison, so this never manufactures a false duplicate).
    """
    base_columns = ["id", "population", "primary_outcome", "result_direction", "study_type", "notes"]
    optional_columns = ["plant_part", "dose", "preparation"]

    def _run(columns):
        return (
            supabase.table("evidence_records")
            .select(", ".join(columns))
            .eq("plant_id", plant_id)
            .eq("target_indication", indication or "")
            .eq("dosage_form", dosage_form or "")
            .eq(id_field, id_value)
            .limit(50)
            .execute()
        )

    remaining_optional = list(optional_columns)
    for _ in range(len(optional_columns) + 1):
        try:
            result = _run(base_columns + remaining_optional)
            return result.data or []
        except Exception as exc:
            missing = _missing_postgrest_column(exc)
            if missing in ("doi", "pmid", "nct_id", "source_id", "plant_id",
                           "target_indication", "dosage_form"):
                # A REQUIRED column is missing — this deployment cannot
                # answer the query at all; never silently proceed.
                return None
            if missing in remaining_optional:
                remaining_optional.remove(missing)
                continue
            raise
    return None


def _find_existing_evidence_by_identity(supabase, plant_id, species, doi, pmid, nct_id,
                                         indication, dosage_form, new_record):
    """PHASE 2 (review round 3, issue 1 fix) — TWO-PHASE insert-time
    dedup using the canonical DOI/PMID/Trial-Registration identity,
    queried BEFORE the pre-existing URL/title-based
    _find_existing_source() lookup.

    Phase 1: find candidate ARTICLE rows sharing the same DOI/PMID/NCT_ID
    (via _fetch_evidence_identity_candidates(), scoped to the same
    plant/indication/dosage_form to keep the query bounded — see that
    function's docstring).

    Phase 2: only treat a candidate as a duplicate when
    deduplication_engine.evidence_contexts_equivalent() says the new
    record and that candidate describe the same scientific context
    (population/primary_outcome/result_direction/study_type/notes/
    plant_part, plus the already-known plant/indication/dosage_form —
    all already guaranteed equal by the phase-1 query filter). This
    deliberately does NOT re-derive or re-compare article identity here
    (i.e., does not call compute_evidence_identity() and compare the
    full string) — article equivalence was already established in
    phase 1 by the exact DOI/PMID/NCT_ID match, and re-deriving a
    title+year+author-based article key from a candidate row that has
    no author data available (evidence_records carries no author
    column) would spuriously fail to match a record whose OWN new-side
    first_author happens to be populated — a real bug caught during
    review round 3 testing. evidence_contexts_equivalent() sidesteps
    this by only ever comparing the non-article scientific dimensions.

    Two Evidence rows about the same article, same plant, same
    indication, same dosage form, but a different outcome or direction
    or population, are NOT collapsed — this is exactly the distinction
    article_identity vs. evidence_identity exists to preserve (see
    PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md).

    Degrades safely: returns None (falls through to the pre-existing
    URL/title path) whenever no DOI/PMID/NCT_ID is present, the
    identifier column doesn't exist yet on this deployment, or no
    candidate's evidence context matches. On any ambiguity — a query
    that cannot be resolved — the record is preferred to be KEPT (not
    silently treated as a duplicate).
    """
    if not any([doi, pmid, nct_id]):
        return None

    if doi:
        id_field, id_value = "doi", doi
    elif pmid:
        id_field, id_value = "pmid", pmid
    else:
        id_field, id_value = "nct_id", nct_id

    candidates = _fetch_evidence_identity_candidates(
        supabase, plant_id, indication, dosage_form, id_field, id_value
    )
    if candidates is None:
        return None

    for candidate in candidates:
        candidate_row = {
            "Scientific_Name": species,
            "Target_Indication": indication,
            "Dosage_Form": dosage_form,
            "Population": candidate.get("population"),
            "Primary_Outcome": candidate.get("primary_outcome"),
            "Result_Direction": candidate.get("result_direction"),
            "Study_Type": candidate.get("study_type"),
            "Notes": candidate.get("notes"),
            "Plant_Part": candidate.get("plant_part"),
            "Dose": candidate.get("dose"),
            "Preparation": candidate.get("preparation"),
        }
        if evidence_contexts_equivalent(new_record, candidate_row):
            return candidate["id"]

    return None


def _find_existing_evidence_by_fuzzy_title(supabase, plant_id, species, indication, dosage_form,
                                            article_title, publication_year, first_author, new_record):
    """PHASE 2 (review round, issue 5; review round 3, issues 1 and 4) —
    bounded insert-time fallback, used ONLY when save_evidence_record()
    has no DOI/PMID/NCT_ID to check (_find_existing_evidence_by_identity()
    above already covers the strong-identifier case).

    NEVER a full-table scan: queries the `sources` table narrowed by
    `year` when a publication year is known, always capped at a bounded
    page size (`limit(200)`) even when it isn't; article-level candidate
    matching runs in Python via articles_equivalent() — the SAME
    function read-time dedup uses, so the two policies cannot drift
    apart.

    REVIEW ROUND 3, ISSUE 4 — first author honesty: the `sources` table
    has no author column at all, so `first_author` on the EXISTING side
    of this comparison is always unavailable. articles_equivalent()
    accounts for this itself (see its docstring): when an author cannot
    be verified on both sides, it requires the stricter
    FUZZY_TITLE_SIMILARITY_THRESHOLD_UNVERIFIED_AUTHOR instead of
    silently skipping the author check. This function does not, and
    must not, claim a title+year+author match here — it is a
    title+year match with a raised bar, and is documented as such.

    REVIEW ROUND 3, ISSUE 1 — once a fuzzy-equivalent article candidate
    is found, this now ALSO fetches that candidate evidence row's
    population/primary_outcome/result_direction/study_type/notes/
    plant_part and requires evidence_contexts_equivalent() to agree
    (the same non-article scientific-context comparison
    _find_existing_evidence_by_identity() uses) before treating it as a
    duplicate — a fuzzy-matched article with a genuinely different
    outcome/direction/population is no longer collapsed.

    Degrades to None (falls through to the pre-existing
    _find_existing_source() URL/title path) when no article_title is
    available, when the query itself fails, or when no candidate's
    article AND evidence context both match.
    """
    if not article_title:
        return None

    query = supabase.table("sources").select("id, title, year")
    if publication_year:
        query = query.eq("year", publication_year)

    try:
        result = query.limit(200).execute()
    except Exception:
        return None

    candidate_a = {
        "article_title": article_title,
        "publication_year": publication_year,
        "first_author": first_author,
    }

    for source_row in (result.data or []):
        candidate_b = {
            "article_title": source_row.get("title"),
            "publication_year": source_row.get("year"),
            # No first_author key here — the `sources` table carries
            # none; articles_equivalent() treats this as "unverifiable"
            # and raises its similarity bar accordingly (see its
            # docstring), rather than silently proceeding as if the
            # author matched.
        }
        if not articles_equivalent(candidate_a, candidate_b):
            continue

        source_id = source_row.get("id")
        if source_id is None:
            continue

        evidence_candidates = _fetch_evidence_identity_candidates(
            supabase, plant_id, indication, dosage_form, "source_id", source_id
        )
        if not evidence_candidates:
            continue

        for candidate in evidence_candidates:
            candidate_row = {
                "Scientific_Name": species,
                "Target_Indication": indication,
                "Dosage_Form": dosage_form,
                "Population": candidate.get("population"),
                "Primary_Outcome": candidate.get("primary_outcome"),
                "Result_Direction": candidate.get("result_direction"),
                "Study_Type": candidate.get("study_type"),
                "Notes": candidate.get("notes"),
                "Plant_Part": candidate.get("plant_part"),
                "Dose": candidate.get("dose"),
                "Preparation": candidate.get("preparation"),
            }
            if evidence_contexts_equivalent(new_record, candidate_row):
                return candidate["id"]

    return None


def save_evidence_record(record):
    supabase = get_supabase_client()

    # PHASE 2 (review round, issue 1) — the canonical adapter genuinely
    # runs here, in production, before any field of `record` is read.
    # canonicalize_evidence_record() round-trips through
    # EvidenceRecord.from_legacy_dict()/.to_legacy_dict(); the result is
    # still a legacy-compatible dict (same keys downstream code already
    # reads), so nothing below this line needed to change.
    record = canonicalize_evidence_record(record)

    source_url = record.get("Source_URL", "")
    source_title = record.get("Source_Title", "")

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

    doi_norm = normalize_doi(record.get("DOI"))
    pmid_norm = normalize_pmid(record.get("PMID"))
    nct_norm = normalize_trial_registration(record.get("NCT_ID"))

    # PHASE 2 — canonical identity check, BEFORE the pre-existing
    # URL/title-based source lookup. See _find_existing_evidence_by_identity()
    # docstring; purely additive, degrades to None (falls through to the
    # unchanged legacy path below) whenever no DOI/PMID/NCT_ID is present
    # or the columns don't exist yet on this deployment.
    identity_match_id = _find_existing_evidence_by_identity(
        supabase=supabase,
        plant_id=plant_id,
        species=record.get("Scientific_Name", ""),
        doi=doi_norm,
        pmid=pmid_norm,
        nct_id=nct_norm,
        indication=record.get("Target_Indication", ""),
        dosage_form=record.get("Dosage_Form", ""),
        new_record=record,
    )
    if identity_match_id is not None:
        return identity_match_id

    # PHASE 2 (review round, issue 5) — bounded title+year+author
    # fallback, ONLY attempted when no strong identifier exists at all
    # (mirrors the "insert-time" column of the priority table in
    # PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md §5, now actually true for
    # both insert-time and read-time).
    if not any([doi_norm, pmid_norm, nct_norm]):
        fuzzy_match_id = _find_existing_evidence_by_fuzzy_title(
            supabase=supabase,
            plant_id=plant_id,
            species=record.get("Scientific_Name", ""),
            indication=record.get("Target_Indication", ""),
            dosage_form=record.get("Dosage_Form", ""),
            article_title=record.get("Source_Title"),
            publication_year=record.get("Source_Year"),
            first_author=get_first_present(
                record, "First_Author", "first_author", "Authors", "authors"
            ),
            new_record=record,
        )
        if fuzzy_match_id is not None:
            return fuzzy_match_id

    existing_source_id = _find_existing_source(
        supabase=supabase,
        url=source_url,
        title=source_title,
    )

    # PHASE 2 (review round 4, legacy-bypass fix) — the pre-existing
    # URL/title-based source lookup above is STILL used to find/reuse a
    # `sources` row (that part is unchanged and correct: the same
    # article should not get a second `sources` row just because a
    # second Evidence context is being added for it). What changed:
    # this legacy path used to ALSO decide Evidence duplication by
    # itself, via a bare source_id+plant_id+indication+dosage_form
    # lookup with no evidence-context comparison at all — exactly the
    # same class of bug already fixed for the DOI/PMID/NCT_ID and fuzzy
    # -title paths above, just left unfixed on this third, older path.
    # It is now brought in line with those: candidates sharing this
    # source_id are fetched with full context via the SAME
    # _fetch_evidence_identity_candidates() helper the other two paths
    # use (no new, parallel lookup logic), and a match is only returned
    # when deduplication_engine.evidence_contexts_equivalent() agrees.
    # A genuinely different Evidence context for the same article now
    # correctly REUSES existing_source_id (no second `sources` row) but
    # still INSERTS a new `evidence_records` row — see below.
    if existing_source_id:
        evidence_candidates = _fetch_evidence_identity_candidates(
            supabase, plant_id, record.get("Target_Indication", ""),
            record.get("Dosage_Form", ""), "source_id", existing_source_id,
        )
        if evidence_candidates:
            for candidate in evidence_candidates:
                candidate_row = {
                    "Scientific_Name": record.get("Scientific_Name", ""),
                    "Target_Indication": record.get("Target_Indication", ""),
                    "Dosage_Form": record.get("Dosage_Form", ""),
                    "Population": candidate.get("population"),
                    "Primary_Outcome": candidate.get("primary_outcome"),
                    "Result_Direction": candidate.get("result_direction"),
                    "Study_Type": candidate.get("study_type"),
                    "Notes": candidate.get("notes"),
                    "Plant_Part": candidate.get("plant_part"),
                    "Dose": candidate.get("dose"),
                    "Preparation": candidate.get("preparation"),
                }
                if evidence_contexts_equivalent(record, candidate_row):
                    return candidate["id"]
        # No candidate matched (or the candidate query itself was
        # ambiguous/unresolvable — _fetch_evidence_identity_candidates()
        # returning None is handled identically to an empty list here:
        # both mean "cannot confirm a duplicate," and per the review's
        # explicit instruction, a false duplicate is more dangerous than
        # a temporary duplicate, so the record is kept and a new
        # evidence_records row is inserted below) — existing_source_id
        # is still reused, just not treated as Evidence-duplicating.

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
        # PHASE 2 (review round 5) — migrations/0006_add_dose_preparation.sql.
        # Previously read and compared by
        # deduplication_engine.compute_evidence_identity()/
        # evidence_contexts_equivalent() since round 1, but never actually
        # persisted anywhere — meaning the database side of every identity
        # comparison always saw these as empty regardless of what the new
        # record carried. "Preparation" is NEVER read from
        # record.get("Extraction_Method") — the two are distinct concepts;
        # see the migration file's header for the full reasoning.
        "dose": record.get("Dose") or None,
        "preparation": record.get("Preparation") or None,
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
            # PHASE 2 (review round 5) — migrations/0006_add_dose_preparation.sql.
            # item.get(...) returns None for both an unmigrated table
            # (column absent) and a migrated table with a genuinely null
            # value — same degrade-safely behavior as every other Phase 2
            # optional column above.
            "Dose": item.get("dose"),
            "Preparation": item.get("preparation"),

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
