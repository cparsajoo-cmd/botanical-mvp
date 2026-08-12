"""
standard_evidence_builder — Task 10.2 adds evidence-ITEM-level
Preparation Applicability alongside the pre-existing
Direct_For_Selected_Product / Directness_Reason fields.

WHY THIS LIVES HERE, NOT A NEW MODULE
build_standard_evidence() is already the single place the active
evidence_records pathway computes an applicability-shaped signal
(Direct_For_Selected_Product). Task 10.2 extends that same function's
neighborhood, following the same "extend, don't create a parallel
engine" rule already applied to structured_rationale.py (Sprint 4) and
occurrence_seed.py (Task 7).

WHY Direct_For_Selected_Product IS UNCHANGED, NOT REPLACED
Direct_For_Selected_Product/Directness_Reason are preserved byte-for-byte
(same two branches, same strings) for backward compatibility with
every existing caller and every already-persisted evidence_records row.
Applicability_Classification is a SEPARATE, more conservative signal:
Direct_For_Selected_Product only ever looks at dosage form; the new
classification also considers indication, and requires more evidence
before it will call anything "directly" applicable. The two fields can
and will disagree on some rows — that is expected, not a bug (e.g. a
row can be Direct_For_Selected_Product="Yes" while
Applicability_Classification="Partially applicable", because plant
part/extraction data — required for the new classification's top tier
— is not tracked anywhere in this schema yet; see DIMENSION NOTES).

CONSERVATIVE-BY-CONSTRUCTION
Per the explicit instruction: indication+dosage-form match ALONE can
never produce DIRECTLY_APPLICABLE. Direct applicability requires every
dimension in REQUIRED_DIMENSIONS to be evaluable (both a selected/
expected value AND a detected value present) AND matching. Missing
data is never inferred — a dimension with no detected value is recorded
as missing, never guessed at or defaulted to a match.

DIMENSION NOTES (audited against the active evidence_records schema,
see database.save_evidence_record()/load_evidence_records() — no
column name below is invented)
  - indication:  selected = Target_Indication, detected =
    Detected_Indications / Target_Indication_Detected. Available today.
  - dosage_form: selected = Dosage_Form, detected =
    Detected_Dosage_Forms / Detected_Dosage_Form. Available today.
  - plant_part:  no column exists anywhere in the active evidence_records
    schema (STANDARD_FIELDS, build_standard_evidence's own output, and
    database.py's insert/select column lists were all checked — none
    carry a plant-part value). This function reads record.get("Plant_Part")
    defensively (forward-compatible if a future change adds it) but
    under the CURRENT schema this dimension is always "missing" — never
    fabricated as a match.
  - extraction_or_solvent: same situation as plant_part — no
    Extraction_Method/solvent column exists in evidence_records today
    (plant_compound_extractor.py's extraction/solvent fields belong to
    a completely separate table, plant_compounds, not evidence_records).
    Read defensively via record.get("Extraction_Method")/
    record.get("Extraction_Solvent"); always "missing" under the
    current schema.

Because two of the four required dimensions are structurally absent
from today's schema, DIRECTLY_APPLICABLE is not reachable with today's
data — that is the conservative, honest result of applying this rule
to real data, not a bug in the rule itself. See
test_standard_evidence_builder.py (test 5 of Task 10.2's required
tests) for the explicit regression lock on this.
"""

from data_contracts import (
    EvidenceApplicability,
    EvidenceHierarchyLevel,
    MarketVerificationStatus,
    RegulatoryRecord,
    ScientificEvidence,
)
from typing import Any, Mapping, Optional

import pandas as pd

# Every dimension considered "material" to preparation applicability.
# route/population/dose/DER/standardization/chemotype are deliberately
# NOT included here: route and population are proposed-product/session
# -level concepts (question_understanding_engine.standardize_project_
# definition()), never attached to an individual evidence_records row,
# and dose/DER/standardization/chemotype have no column anywhere in the
# active schema (product_development_concept.py already documents this
# as NOT_TRACKED). Listing a dimension this function cannot actually
# read from any real column would be inventing data, not evaluating it.
REQUIRED_DIMENSIONS = ("indication", "dosage_form", "plant_part", "extraction_or_solvent")

# Dimensions whose MISMATCH is treated as decision-relevant enough to
# justify NOT_APPLICABLE. plant_part/extraction_or_solvent can currently
# only ever be "missing" (see module docstring), never "mismatched", so
# in practice only these two ever drive a NOT_APPLICABLE call today —
# the set is defined generically so it stays correct if the schema
# grows.
CRITICAL_MISMATCH_DIMENSIONS = ("indication", "dosage_form")


def _dimension_status(selected, detected):
    """Returns ("match"|"mismatch"|"missing", detail_str).

    Never infers a value: "missing" is returned whenever EITHER side is
    empty — there is no case where an empty value is treated as a match.
    """
    selected = (selected or "").strip().lower()
    detected = (detected or "").strip().lower()

    if not selected or not detected:
        return "missing", None

    if selected in detected or detected in selected:
        return "match", None

    return "mismatch", f"detected '{detected}' vs selected '{selected}'"


def classify_evidence_applicability(record, selected_form, selected_indication,
                                     detected_form, detected_indication):
    """Task 10.2 — evidence-ITEM-level applicability classification.

    Takes the same selected_*/detected_* strings build_standard_evidence()
    already computes for Direct_For_Selected_Product, plus the raw
    `record` (for the defensive, currently-always-missing plant_part/
    extraction reads — see module docstring).

    Returns a dict with exactly these keys:
      classification         — EvidenceApplicability value (str)
      rationale               — human-readable explanation naming the
                                 evaluated/missing/mismatched dimensions
                                 and the rule applied
      evaluated_dimensions    — list[str], dimensions where both a
                                 selected and detected value existed
      missing_dimensions      — list[str], dimensions that could not be
                                 evaluated (with the specific reason)
      detected_mismatches     — list[str], dimensions with a confirmed,
                                 decision-relevant mismatch
    """
    plant_part_detected = record.get("Plant_Part") or record.get("plant_part") or ""
    extraction_detected = (
        record.get("Extraction_Method") or record.get("extraction_method") or
        record.get("Extraction_Solvent") or record.get("extraction_solvent") or ""
    )

    dimension_inputs = {
        "indication": (selected_indication, detected_indication),
        "dosage_form": (selected_form, detected_form),
        # No "selected" plant part / extraction exists anywhere in the
        # active project-definition or evidence schema (see module
        # docstring) — passing "" as the selected side means
        # _dimension_status() will always report "missing" for these
        # two under the current schema, honestly, rather than fabricate
        # a comparison that cannot actually be made.
        "plant_part": ("", plant_part_detected),
        "extraction_or_solvent": ("", extraction_detected),
    }

    evaluated_dimensions = []
    missing_dimensions = []
    detected_mismatches = []
    statuses = {}

    for dimension in REQUIRED_DIMENSIONS:
        selected_value, detected_value = dimension_inputs[dimension]
        status, detail = _dimension_status(selected_value, detected_value)
        statuses[dimension] = status

        if status == "match":
            evaluated_dimensions.append(dimension)
        elif status == "mismatch":
            evaluated_dimensions.append(dimension)
            label = f"{dimension} ({detail})" if detail else dimension
            detected_mismatches.append(label)
        else:
            reason = (
                "no expected/selected value defined for this dimension in the "
                "active pipeline"
                if not selected_value else
                "no detected value found in this evidence item"
            )
            missing_dimensions.append(f"{dimension} ({reason})")

    critical_mismatch = any(
        statuses.get(dim) == "mismatch" for dim in CRITICAL_MISMATCH_DIMENSIONS
    )

    matched_count = sum(1 for s in statuses.values() if s == "match")
    missing_count = sum(1 for s in statuses.values() if s == "missing")

    if critical_mismatch:
        classification = EvidenceApplicability.NOT_APPLICABLE
        rule = (
            "NOT_APPLICABLE: a decision-relevant mismatch was confirmed on "
            f"{', '.join(dim for dim in CRITICAL_MISMATCH_DIMENSIONS if statuses.get(dim) == 'mismatch')}."
        )
    elif missing_count == 0 and matched_count == len(REQUIRED_DIMENSIONS):
        classification = EvidenceApplicability.DIRECTLY_APPLICABLE
        rule = (
            "DIRECTLY_APPLICABLE: all required dimensions "
            f"({', '.join(REQUIRED_DIMENSIONS)}) were evaluated and matched."
        )
    elif matched_count >= 2:
        classification = EvidenceApplicability.PARTIALLY_APPLICABLE
        rule = (
            "PARTIALLY_APPLICABLE: indication and dosage form both match the "
            "selected product, but one or more required dimensions "
            f"({', '.join(missing_dimensions) or 'none'}) could not be evaluated — "
            "direct applicability requires every required dimension to be evaluated."
        )
    elif matched_count >= 1:
        classification = EvidenceApplicability.INDIRECTLY_RELEVANT
        rule = (
            "INDIRECTLY_RELEVANT: only one required dimension could be confirmed "
            "as matching; too little was evaluable to call this partially applicable."
        )
    else:
        classification = EvidenceApplicability.NOT_ASSESSABLE
        rule = (
            "NOT_ASSESSABLE: none of the required dimensions "
            f"({', '.join(REQUIRED_DIMENSIONS)}) had both a selected/expected value "
            "and a detected value available for comparison."
        )

    rationale_parts = [rule]
    if evaluated_dimensions:
        rationale_parts.append(f"Evaluated: {', '.join(evaluated_dimensions)}.")
    if missing_dimensions:
        rationale_parts.append(f"Missing: {', '.join(missing_dimensions)}.")
    if detected_mismatches:
        rationale_parts.append(f"Mismatches: {', '.join(detected_mismatches)}.")

    return {
        "classification": classification.value,
        "rationale": " ".join(rationale_parts),
        "evaluated_dimensions": evaluated_dimensions,
        "missing_dimensions": missing_dimensions,
        "detected_mismatches": detected_mismatches,
    }


def build_standard_evidence(record):
    # Selected/requested product context is metadata about WHY a source was
    # retrieved, not a fact about WHAT the study used.  Prefer the dedicated
    # request keys when present; legacy callers that still only provide
    # Dosage_Form/Target_Indication keep working via the fallback.
    selected_form = str(
        record.get("Requested_Dosage_Form") or record.get("Dosage_Form", "")
    ).strip().lower()
    selected_indication = str(
        record.get("Requested_Target_Indication") or record.get("Target_Indication", "")
    ).strip().lower()

    detected_form = (
        str(record.get("Detected_Dosage_Forms", "")) or
        str(record.get("Detected_Dosage_Form", ""))
    ).strip()

    detected_indication = (
        str(record.get("Detected_Indications", "")) or
        str(record.get("Target_Indication_Detected", "")) or
        str(record.get("Target_Indication", ""))
    ).strip()

    detected_form_lower = detected_form.lower()

    # --- Direct_For_Selected_Product / Directness_Reason — UNCHANGED,
    # byte-for-byte identical to pre-Task-10.2 behavior. Do not merge
    # this with the new classification below; see module docstring for
    # why the two are deliberately allowed to disagree.
    if selected_form and selected_form in detected_form_lower:
        direct = "Yes"
        reason = "Detected dosage form matches selected product dosage form."
    elif detected_form:
        direct = "No"
        reason = f"Detected dosage form differs: {detected_form}"
    else:
        direct = "Unknown"
        reason = "Dosage form not clearly detected."

    score = int(record.get("Evidence_Score", 0) or 0)

    # --- Task 10.2 — Evidence-level Preparation Applicability (new,
    # additive; never overwrites Direct_For_Selected_Product/
    # Directness_Reason above).
    applicability = classify_evidence_applicability(
        record=record,
        selected_form=selected_form,
        selected_indication=selected_indication,
        detected_form=detected_form_lower,
        detected_indication=detected_indication.lower(),
    )

    standard = {
        "Plant": record.get("Scientific_Name", ""),
        "Study_Type": record.get("Evidence_Type", "Unknown"),
        "Study_Model": record.get("Study_Model", "Unknown"),
        "Dosage_Form_Detected": detected_form,
        "Target_Indication_Detected": detected_indication,
        "Population": record.get("LLM_Population", ""),
        # Phase 2 (IMPLEMENTATION_PLAN.md) — previously this always took
        # LLM_Sample_Size, even when a connector (ClinicalTrials.gov's
        # enrollment count, hand-copied through by
        # evidence_standardizer.py) already provided a real Sample_Size
        # on `record`. That unconditionally overwrote the connector's own
        # value with an empty string whenever no LLM ran. The
        # connector-provided value — more literal, not inferred — now
        # takes precedence; LLM_Sample_Size is only used when nothing
        # else has already set it.
        "Sample_Size": record.get("Sample_Size") or record.get("LLM_Sample_Size", ""),
        "Comparator": record.get("LLM_Comparator", ""),
        # Literal connector/source fields take precedence.  LLM-derived
        # values are fallbacks only, matching the Sample_Size policy above.
        "Primary_Outcome": record.get("Primary_Outcome") or record.get("LLM_Main_Outcome", ""),
        # Root-cause fix (2026-08-11, external audit point 4, confirmed
        # by direct trace: this line was the actual cause even after
        # evidence_standardizer.py's own copy-through was removed, since
        # this function runs LAST and re-introduced the exact same
        # mixing). Result_Direction/Safety_Signal are NOT included in the
        # Sample_Size/Primary_Outcome "LLM as fallback" policy above --
        # those two feed canonical_scientific_assertion.py's
        # resolve_record_direction() precedence (source_result_direction
        # > llm_result_direction > legacy), which only works if
        # Result_Direction genuinely means "what the source said" and
        # never silently absorbs the LLM's own inference. Blending them
        # here would make resolve_record_direction() see LLM output and
        # treat it as if the source had reported it directly -- the same
        # failure mode already found and fixed once in
        # backfill_canonical_assertions.py (2026-08-10) and in
        # evidence_standardizer.py above; this was the third and, per the
        # external audit, final place it survived.
        "Result_Direction": record.get("Result_Direction") or "",
        "Safety_Signal": record.get("Safety_Signal") or "",
        # Preserved as their own genuinely-separate output keys (previously
        # this function only ever read them as a fallback for the two
        # lines above and never passed them through standalone -- meaning
        # the LLM's real output was silently dropped entirely once it
        # could no longer masquerade as source data). Downstream
        # persistence (database.py) picking these up is a separate,
        # later step -- out of scope here; today llm_result_direction/
        # llm_safety_signal are populated for existing rows by
        # backfill_canonical_assertions.py, which will do the same for
        # any row where these arrive empty at initial ingest.
        "LLM_Result_Direction": record.get("LLM_Result_Direction") or "",
        "LLM_Safety_Signal": record.get("LLM_Safety_Signal") or "",
        "Adverse_Events": record.get("Adverse_Events"),
        "Interactions_Structured": record.get("Interactions_Structured"),
        "Effect_Size": record.get("Effect_Size"),
        "P_Value": record.get("P_Value"),
        "Administration_Route": record.get("Administration_Route"),
        "Plant_Part": record.get("Plant_Part"),
        "Extraction_Method": record.get("Extraction_Method"),
        "Duration": record.get("Duration"),
        "Evidence_Level": record.get("Evidence_Level", "Unknown"),
        "Direct_For_Selected_Product": direct,
        "Directness_Reason": reason,
        "Evidence_Score": score,
        "Applicability_Classification": applicability["classification"],
        "Applicability_Rationale": applicability["rationale"],
        "Applicability_Evaluated_Dimensions": "; ".join(applicability["evaluated_dimensions"]),
        "Applicability_Missing_Dimensions": "; ".join(applicability["missing_dimensions"]),
        "Applicability_Detected_Mismatches": "; ".join(applicability["detected_mismatches"]),
    }

    record.update(standard)
    return record


# ======================================================================
# Task 11.1 — ScientificEvidence adapter.
#
# WHY THIS LIVES HERE, NOT A NEW MODULE
# Same reasoning as classify_evidence_applicability() above: this is
# the one module that already turns an active evidence_records row
# into a named, typed shape (build_standard_evidence()'s own PascalCase
# dict). build_scientific_evidence() is the next small step past that
# — the SAME dict, reshaped into data_contracts.ScientificEvidence
# instead of a bare dict — not a parallel construction path.
#
# WHAT THIS DOES NOT DO
# - Does not add any new Supabase column. Every field it reads already
#   exists under its current PascalCase name (Source_Type, Evidence_Type,
#   Population, Comparator, Primary_Outcome, Evidence_Level,
#   Evidence_Record_ID, Applicability_*) — this function only RESHAPES
#   already-persisted/already-in-memory data; it never asks database.py
#   to write or read a new field.
# - Does not infer, parse, or guess any field this pipeline does not
#   already carry explicitly. dose/duration/intervention/sample_size/
#   statistical_result/risk_of_bias/plant_identity_verified/
#   extract_characterized/relevance_to_dosage_form/
#   relevance_to_indication/confidence_score/is_negative_or_contradictory/
#   negative_finding_type stay at their dataclass defaults (None/False/[])
#   — the Task 11 audit's field-by-field mapping table documents why
#   each of these has "no current source" or is a "semantically unsafe
#   mapping" this function deliberately does not attempt.
# ======================================================================

# Conservative Evidence_Level -> EvidenceHierarchyLevel normalization.
# Evidence_Level is a loosely-controlled free string with several real
# provenances (LLM output: "Very High"/"High"/"Moderate"/"Low"/
# "Very Low"/"Traditional"/"Unknown"; per-connector labels: "Supporting"/
# "Not available"/"Checked, not found"/"Listed in official EMA HMPC
# inventory" — confirmed by grepping every "Evidence_Level": assignment
# in the repo) — an ordinal EVIDENCE-QUALITY scale, not the STUDY-TYPE
# categories EvidenceHierarchyLevel actually encodes. There is no safe,
# deterministic correspondence between a quality judgment like "High"
# and any specific study type (a "High"-quality case series and a
# "High"-quality systematic review are not the same hierarchy tier), so
# only the two values below — which are genuinely, unambiguously about
# traditional/regulatory-monograph use rather than a quality judgment —
# are mapped. Every other value, including every quality-ordinal value
# and "Unknown", normalizes to None rather than guess.
_EVIDENCE_LEVEL_TO_HIERARCHY = {
    "traditional": EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH,
    "listed in official ema hmpc inventory": EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH,
}

# Task 11.1 correction — a single, reusable definition of "missing",
# used everywhere build_scientific_evidence()/_build_scientific_evidence_index()
# read a scalar field. Before this correction, `record.get("Source_Type") or None`
# -style checks silently let a pandas NaN through: float('nan') is
# TRUTHY in Python, so `nan or None` evaluates to `nan`, not `None` —
# the exact bug this fixes. A row loaded via .iterrows()/.to_dict() on
# a DataFrame with any missing cell in a column produces float('nan')
# for that cell, not None or "" — this is normal, expected pandas
# behavior, not a data-quality problem, but every reader of a
# DataFrame row must account for it explicitly.
_MISSING_STRING_TOKENS = {"nan", "none", "null", "na", "n/a"}


def normalize_missing_value(value):
    """Treats as missing (returns None), and NEVER infers a replacement
    value for:
      - None
      - float NaN / pandas NA / NaT (via pd.isna())
      - "" or whitespace-only strings
      - the literal strings "nan"/"none"/"null"/"na"/"n/a" (case-
        insensitive) — the same tokens BotanicalRDCandidateEngine._pick()
        already treats as missing, so a value already stringified
        somewhere upstream (e.g. str(float('nan')) == "nan") is still
        caught, not just genuine NaN objects.

    Any other value (including 0, False, and non-empty strings) is
    returned completely unchanged.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        # pd.isna() raises for some array-like inputs — not a concern
        # for the scalar fields this helper is used on; fail open
        # (treat as not-missing) rather than raise for any unexpected
        # non-scalar type.
        pass
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in _MISSING_STRING_TOKENS:
            return None
    return value


def normalize_evidence_level(evidence_level):
    """Conservative Evidence_Level (free string) -> EvidenceHierarchyLevel
    (enum) normalization. Returns None for any value not in the
    explicit, documented map above — including "Unknown", "", missing
    values (None/NaN/"nan"), and every evidence-quality-ordinal value
    this function does not attempt to guess a study type for.
    """
    evidence_level = normalize_missing_value(evidence_level)
    if evidence_level is None:
        return None
    key = str(evidence_level).strip().lower()
    return _EVIDENCE_LEVEL_TO_HIERARCHY.get(key)


def _split_dimension_string(value):
    """Reverses the "; ".join(...) applied when the Applicability_*
    dimension/mismatch fields were persisted (see build_standard_evidence()
    above) — the inverse of that join, not a new parsing rule."""
    value = normalize_missing_value(value)
    if value is None:
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


def build_scientific_evidence(record):
    """Task 11.1 — adapts an active evidence_records row (the same
    PascalCase dict shape build_standard_evidence() produces, and
    database.load_evidence_records() reloads) into a
    data_contracts.ScientificEvidence instance.

    Maps ONLY fields this pipeline already carries under an existing
    name — no new Supabase column, no inferred value. Every field with
    no current source in the active schema is left at its dataclass
    default (None / False / empty list), never fabricated. See this
    module's own docstring, immediately above, for exactly which fields
    that applies to and why.
    """
    applicability_raw = normalize_missing_value(record.get("Applicability_Classification"))
    applicability_classification = None
    if applicability_raw is not None:
        try:
            applicability_classification = EvidenceApplicability(applicability_raw)
        except ValueError:
            # A classification string that doesn't match any current
            # EvidenceApplicability value (e.g. a foreign/corrupted
            # row) — left None rather than guessed, same conservative
            # rule as normalize_evidence_level() above.
            applicability_classification = None

    # Task 11.1 correction — normalize BEFORE stringifying. The
    # pre-correction code checked `evidence_record_id not in (None, "")`
    # and only then called str(...) — a NaN evidence_record_id (a real,
    # observed pandas behavior, not a hypothetical) passed that check
    # (NaN is neither None nor "") and produced the literal string
    # "nan" as source_record_id. Normalizing first closes this exactly.
    evidence_record_id = normalize_missing_value(record.get("Evidence_Record_ID"))

    return ScientificEvidence(
        source_type=normalize_missing_value(record.get("Source_Type")),
        doi_pmid_url=normalize_missing_value(record.get("Source_URL")),
        study_type=(
            normalize_missing_value(record.get("Evidence_Type"))
            or normalize_missing_value(record.get("Study_Type"))
        ),
        population=normalize_missing_value(record.get("Population")),
        comparator=normalize_missing_value(record.get("Comparator")),
        outcome=normalize_missing_value(record.get("Primary_Outcome")),
        evidence_hierarchy_level=normalize_evidence_level(record.get("Evidence_Level")),
        source_record_id=(
            str(evidence_record_id) if evidence_record_id is not None else None
        ),
        applicability_classification=applicability_classification,
        applicability_rationale=normalize_missing_value(record.get("Applicability_Rationale")),
        applicability_evaluated_dimensions=_split_dimension_string(
            record.get("Applicability_Evaluated_Dimensions")
        ),
        applicability_missing_dimensions=_split_dimension_string(
            record.get("Applicability_Missing_Dimensions")
        ),
        applicability_detected_mismatches=_split_dimension_string(
            record.get("Applicability_Detected_Mismatches")
        ),
        # Deliberately left at dataclass defaults — no current source in
        # the active evidence_records schema (Task 11 audit §4/§6):
        # sample_size, intervention, dose, duration, statistical_result,
        # plant_identity_verified, extract_characterized, risk_of_bias,
        # relevance_to_dosage_form, relevance_to_indication,
        # confidence_score, is_negative_or_contradictory,
        # negative_finding_type.
    )


# ======================================================================
# Task 13.2A — get_scientific_evidence_by_ids()
#
# WHY THIS LIVES HERE, NOT IN THE ENGINE
# This is a report-time need: given the evidence_record_ids a candidate
# row's Applicability_Summary already carries (Task 10.2), and the
# evidence_df already available via st.session_state (app.py), resolve
# each id to its ScientificEvidence object — WITHOUT the report layer
# ever importing botanical_rd_candidate_engine.py or touching
# BotanicalRDCandidateEngine.scientific_evidence_index (Task 11.1),
# which is engine-instance-scoped and, per the Task 13 audit, not
# reliably alive at report-generation time. standard_evidence_builder.py
# already has zero dependency on the engine and is already the
# canonical owner of build_scientific_evidence() — this function is the
# same adapter, called from a different, stateless entry point.
#
# WHY IT DOES NOT DUPLICATE _build_scientific_evidence_index()
# Both ultimately call the same build_scientific_evidence() for the
# actual object construction — nothing about *how* a ScientificEvidence
# gets built is repeated here. The only new logic in this function is
# the id-membership filter itself (which rows to bother building at
# all), which _build_scientific_evidence_index() has no equivalent of
# because it always builds every row in self.evidence_df.
# ======================================================================

def get_scientific_evidence_by_ids(evidence_record_ids, evidence_df):
    """Task 13.2A — filtered evidence_record_id -> ScientificEvidence
    lookup, for report-time use.

    Parameters
    ----------
    evidence_record_ids : any iterable of requested ids (list, set,
        tuple, generator, pandas Series/Index — anything list()-able).
        Duplicate, None, NaN, pandas-NA, and empty-string entries are
        all safely ignored, not errors.
    evidence_df : the already-loaded evidence DataFrame (the exact
        object at st.session_state["evidence_df"] in the real app, or
        any DataFrame shaped like database.load_evidence_records()'s
        output — same shape build_scientific_evidence() already reads
        elsewhere in this module).

    Returns
    -------
    dict[str, ScientificEvidence] — ONLY the requested ids that were
    actually resolvable. A requested id with no matching row is simply
    absent from the result — never an error, never a placeholder
    value, never a partially-built object standing in for "not found".

    GUARANTEES
    - Never raises, for any input shape covered by the constraints
      below — always degrades to {} or to a partial result, never an
      exception escaping this function.
    - Never mutates evidence_df — read-only throughout (.iterrows()
      and .get() only; no .loc[]= / .at[]= / in-place operation of any
      kind).
    - Every value in the result is a real ScientificEvidence instance
      built via build_scientific_evidence() — identical construction
      logic to every other caller of that function; nothing here
      constructs one differently, and nothing here recomputes
      applicability, hierarchy, confidence, or any other scientific
      judgment — those are read verbatim from the row, exactly as
      build_scientific_evidence() already does.
    - IDs are normalized via normalize_missing_value() (the same
      helper Task 11.1's correction already established) then
      stringified — the SAME normalization applied to both the
      requested-id list and each row's own id, so "7" (str) and 7
      (int) requested/stored inconsistently still match correctly.
    - Duplicate rows in evidence_df sharing the same id: last-row-wins,
      identical convention to _build_scientific_evidence_index() and
      occurrence_seed.build_occurrence_lookup().
    - A row that fails to build (any exception inside
      build_scientific_evidence(), for any reason) is skipped for that
      one id only — it does not abort the lookup for every other
      requested id.
    """
    result = {}

    if evidence_df is None or not isinstance(evidence_df, pd.DataFrame) or evidence_df.empty:
        return result

    if evidence_record_ids is None:
        return result

    try:
        requested_iterable = list(evidence_record_ids)
    except TypeError:
        # Not actually iterable (e.g. a bare int/float passed by
        # mistake) — treat as "nothing requested" rather than raise.
        return result

    wanted_ids = set()
    for raw_id in requested_iterable:
        normalized = normalize_missing_value(raw_id)
        if normalized is None:
            continue
        wanted_ids.add(str(normalized))

    if not wanted_ids:
        return result

    for _, row in evidence_df.iterrows():
        record_id = normalize_missing_value(row.get("Evidence_Record_ID"))
        if record_id is None:
            record_id = normalize_missing_value(row.get("evidence_record_id"))
        if record_id is None:
            continue

        key = str(record_id)
        if key not in wanted_ids:
            continue

        try:
            result[key] = build_scientific_evidence(row.to_dict())
        except Exception:
            # A malformed/partial row must not crash the whole lookup —
            # skip only this one id, same fail-safe discipline every
            # persistence/adapter module in this repository already
            # follows. row.to_dict() itself cannot raise for a real
            # pandas row; this guards build_scientific_evidence()'s own
            # construction against any unforeseen malformed value.
            continue

    return result


# ======================================================================
# Task 13.2B — build_scientific_evidence_presentation_payload()
#
# WHY THIS LIVES HERE, NOT IN pharma_report_generator.py
# Same reasoning as get_scientific_evidence_by_ids() (Task 13.2A):
# standard_evidence_builder.py is already the canonical owner of every
# ScientificEvidence construction/adapter step (Task 11 audit §10), and
# already has zero dependency on the report layer or the engine. This
# keeps that ownership consistent rather than splitting "build the
# object" and "make the object presentable" across two modules.
#
# WHY THIS EXISTS AT ALL, SEPARATELY FROM get_scientific_evidence_by_ids()
# ScientificEvidence carries two str-Enum fields
# (applicability_classification, evidence_hierarchy_level).
# Empirically verified (see the Task 13.2 audit): naive string
# interpolation of a (str, Enum) member — f"{x}", str(x), and even
# dataclasses.asdict(x)'s own output — renders the Python repr
# ("EvidenceApplicability.PARTIALLY_APPLICABLE"), NOT the human-facing
# value ("Partially applicable"). This function is the one place that
# conversion happens, exactly mirroring the precedent
# pharma_report_generator._format_gate_results_section() already
# established for GateStatus (`status.value if hasattr(status,
# "value") else status`) — not a new pattern, the same one reused.
# ======================================================================

# The exact seven fields this function exposes — deliberately a
# narrower set than ScientificEvidence's own ~25 fields. Every other
# field (dose, duration, risk_of_bias, evidence_hierarchy_level, etc.)
# is left off ON PURPOSE, per this task's "do not include additional
# dataclass fields" constraint — most of them are already documented
# (Task 11 audit) as having no current source and are always None
# anyway; exposing them here would invite a report template to render
# a wall of "None"s that adds no value.
_PRESENTATION_FIELDS = (
    "evidence_record_id",
    "source_type",
    "study_type",
    "population",
    "applicability_classification",
    "applicability_rationale",
    "doi_pmid_url",
)


def build_scientific_evidence_presentation_payload(scientific_evidence_by_id):
    """Task 13.2B — converts a {evidence_record_id: ScientificEvidence}
    mapping (as returned by get_scientific_evidence_by_ids()) into a
    {evidence_record_id: dict} mapping safe for direct use in a
    markdown/report template — plain strings only, no enum objects, no
    additional fields beyond the seven this task approved.

    PURE, READ-ONLY CONVERSION. Never recomputes applicability,
    hierarchy, confidence, or any other scientific judgment — every
    value in the output was already sitting on the ScientificEvidence
    object, verbatim (after enum unwrapping and missing-value
    normalization, which are presentation concerns, not scientific
    ones). Never mutates `scientific_evidence_by_id` or any
    ScientificEvidence object inside it — read-only attribute access
    only.

    Parameters
    ----------
    scientific_evidence_by_id : the mapping produced by
        get_scientific_evidence_by_ids() — {id: ScientificEvidence}.
        Any non-dict input (None, a list, a bare object, etc.) is
        treated as "nothing to convert" and returns {}, never raises.

    Returns
    -------
    dict[str, dict] — one entry per resolvable, well-formed input
    entry. Each inner dict has exactly the seven keys in
    _PRESENTATION_FIELDS above, no more, no fewer. A value with no
    current source (None on the original ScientificEvidence, or
    normalized to missing — NaN/pd.NA/""/"nan" all included) becomes
    the real Python None, never a fabricated placeholder string.

    An entry is skipped (not included in the output, the surrounding
    dict is otherwise unaffected) when:
      - its key is itself missing/NaN/empty (not a usable id to
        preserve), or
      - its value is not actually a ScientificEvidence instance, or
      - converting it raises for any unforeseen reason — the same
        fail-one-entry-not-the-whole-call discipline
        get_scientific_evidence_by_ids() already established.
    """
    result = {}

    if not isinstance(scientific_evidence_by_id, dict):
        return result

    for record_id, evidence in scientific_evidence_by_id.items():
        # Preserve the id UNCHANGED when usable — normalize_missing_value()
        # here is only a validity check (is this id usable at all?), its
        # result is discarded; the original record_id is what's kept,
        # both as the outer key and inside the payload.
        if normalize_missing_value(record_id) is None:
            continue

        if not isinstance(evidence, ScientificEvidence):
            continue

        try:
            classification = evidence.applicability_classification
            classification_value = (
                classification.value if hasattr(classification, "value") else classification
            )
            classification_value = normalize_missing_value(classification_value)

            result[record_id] = {
                "evidence_record_id": record_id,
                "source_type": normalize_missing_value(evidence.source_type),
                "study_type": normalize_missing_value(evidence.study_type),
                "population": normalize_missing_value(evidence.population),
                "applicability_classification": classification_value,
                "applicability_rationale": normalize_missing_value(evidence.applicability_rationale),
                "doi_pmid_url": normalize_missing_value(evidence.doi_pmid_url),
            }
        except Exception:
            # One malformed entry must not abort every other entry —
            # same discipline as get_scientific_evidence_by_ids().
            continue

    return result


# ======================================================================
# Phase 2A (regulatory-normalization audit) — classify_ema_hmpc_signal()
#
# WHY THIS EXISTS
# botanical_rd_candidate_engine._market_status() independently classifies
# a raw EMA_Status text fragment (the field, not a full evidence row —
# it never has access to Source_Type, so it cannot use the
# Source_Type=="Regulatory" eligibility gate build_regulatory_record()
# below relies on). Before Phase 2A, that classification treated ANY
# genuine "listed in HMPC inventory" match as "Regulatory monograph
# exists" — the exact overstatement build_regulatory_record() was
# already written to avoid (inventory presence maps to
# REGULATORY_ASSESSMENT_INVENTORY_LISTED, never to a monograph-exists
# status). This function is now the ONE shared primitive both paths
# rely on for that distinction — build_regulatory_record() below
# consumes it too (via CANONICAL_EMA_SIGNAL_TO_MARKET_STATUS,
# immediately after this function), so there is a single canonical
# rule for "what does this EMA/HMPC text actually claim", not two
# independently-maintained ones.
#
# SCOPE: text classification only — a raw regulatory-signal string in,
# one semantic category out. It does not build a RegulatoryRecord and
# does not require Source_Type; build_regulatory_record() still owns
# the Source_Type=="Regulatory" eligibility gate and RegulatoryRecord
# construction, it just no longer maintains its own separate text-to-
# status table to do the status half of that job. Deliberately
# generic: matches on structural text patterns only, never a plant
# name, indication, or dosage form.
# ======================================================================

def classify_ema_hmpc_signal(raw_text) -> str:
    """Classify a raw EMA/HMPC regulatory-status text fragment (e.g. the
    EMA_Status field produced by ema_regulatory_connector.py, the
    legacy stub's literal "Yes", or an Evidence_Level value such as
    "Listed in official EMA HMPC inventory"/"Checked, not found"/
    "Not available") into one semantic category:

      - "monograph_exists"    — an explicit, AFFIRMATIVE monograph claim
      - "traditional_use"     — traditional-use / well-established-use
                                  regulatory support mentioned
      - "inventory_listed"    — listed in the HMPC assessment inventory
                                  only; NOT a monograph claim
      - "searched_not_found"  — explicitly checked, not present (this
                                  also covers a monograph confirmed
                                  absent after a completed check, e.g.
                                  "monograph not found" — a genuine
                                  negative finding, not an unresolved one)
      - "source_unavailable"  — the lookup/connector itself failed
      - "unknown"             — empty, unrecognized text, OR a monograph
                                  state that is explicitly hedged/
                                  pending/unresolved (draft, under
                                  assessment, status unknown, not yet
                                  established) rather than a completed
                                  negative finding

    NEVER upgrades inventory presence, or a negative/hedged monograph
    mention, to "monograph_exists" — that overstatement is the one
    specific defect this function exists to prevent.

    ORDER IS LOAD-BEARING — evaluated top to bottom, first match wins:
      1) explicit "searched and absent" phrases (covers both general
         inventory/product absence AND a monograph confirmed absent,
         e.g. "no monograph exists", "monograph not found");
      2) connector/lookup failure phrases;
      3) generic unverified/not-evaluated phrases;
      4) structural inventory-listed match (checked BEFORE any generic
         "monograph" keyword, because the real connector's genuine
         inventory-hit text itself contains the word "monograph" only
         as a hedge — "...see source PDF for monograph status" — never
         as a claim; this also makes reclassifying this function's own
         "Listed in EMA HMPC inventory — monograph not established"
         output land back on "inventory_listed", not "unknown", since
         that phrase also names "hmpc inventory");
      5) traditional-use / well-established-use mention;
      6) hedged/pending/unresolved monograph mentions (not established,
         unavailable, status unknown, draft, under assessment/
         evaluation, pending) — checked BEFORE the generic "not
         available" fallback and BEFORE the affirmative monograph
         check, so these never reach either;
      7) generic "not available" (connector/source-level, no
         monograph-specific wording) — source unavailable;
      8) affirmative monograph phrasing — only what is left here can
         become "monograph_exists".
    """
    if not raw_text:
        return "unknown"
    text = str(raw_text).strip().lower()
    if not text:
        return "unknown"

    # 1) Searched and explicitly absent — general, and monograph-specific.
    if any(p in text for p in (
        "not in hmpc inventory", "not found", "not listed", "no match",
        "no monograph exists", "no monograph", "no published monograph",
    )):
        return "searched_not_found"

    # 2) The lookup/connector itself failed to run.
    if any(p in text for p in ("live fetch failed", "lookup unavailable", "could not check", "could not fetch")):
        return "source_unavailable"

    # 3) Generic unverified / not-evaluated states.
    if any(p in text for p in ("not yet verified", "not evaluated", "not independently verified")):
        return "unknown"

    # 4) Structural inventory-listed match — before any "monograph"
    # keyword check, so a caveat mentioning "monograph" inside an
    # inventory-listed sentence still resolves as inventory presence.
    if text == "yes" or "hmpc inventory" in text:
        return "inventory_listed"

    # 5) Traditional-use / well-established-use support.
    if "traditional use" in text or "traditional-use" in text or "well-established use" in text or "well established use" in text:
        return "traditional_use"

    # 6) Hedged / pending / unresolved monograph states — never an
    # affirmative claim, never a completed negative finding either.
    if any(p in text for p in (
        "monograph not established", "monograph unavailable", "monograph not available",
        "monograph status unknown", "monograph unknown", "draft monograph",
        "monograph under assessment", "monograph under evaluation",
        "pending monograph", "monograph pending",
    )):
        return "unknown"

    # 7) Generic source/connector unavailability (no monograph-specific
    # wording reached this point — that was already resolved above).
    if "not available" in text:
        return "source_unavailable"

    # 8) Only genuinely affirmative monograph phrasing reaches here.
    if any(p in text for p in (
        "monograph adopted", "monograph published", "monograph available",
        "monograph exists", "monograph in force", "adopted monograph",
        "published monograph", "has a monograph",
    )):
        return "monograph_exists"

    return "unknown"


# Canonical semantic category (classify_ema_hmpc_signal's return value)
# -> MarketVerificationStatus. The ONE shared mapping both active
# regulatory-normalization paths use — botanical_rd_candidate_engine.
# _market_status() (via the category string directly, for its own
# public string vocabulary) and build_regulatory_record() below (via
# this dict, for the data_contracts enum). Keeping a single dict here
# means a new distinction only ever needs to be added in one place.
CANONICAL_EMA_SIGNAL_TO_MARKET_STATUS = {
    "inventory_listed": MarketVerificationStatus.REGULATORY_ASSESSMENT_INVENTORY_LISTED,
    "monograph_exists": MarketVerificationStatus.REGULATORY_MONOGRAPH_EXISTS,
    "traditional_use": MarketVerificationStatus.TRADITIONAL_USE_STATUS,
    "searched_not_found": MarketVerificationStatus.NO_VERIFIED_PRODUCT_FOUND,
    "source_unavailable": MarketVerificationStatus.SOURCE_UNAVAILABLE,
    "unknown": MarketVerificationStatus.UNKNOWN,
}


# ======================================================================
# Task 14.1 — build_regulatory_record()
#
# WHY THIS LIVES HERE, NOT A NEW MODULE
# Same reasoning as every prior activation in this module
# (classify_evidence_applicability(), build_scientific_evidence()):
# standard_evidence_builder.py is already the canonical, stateless
# adapter-owner for the active evidence_records pathway, with zero
# dependency on the engine, Streamlit, persistence, scoring, or gates.
#
# WHY THIS IS NARROWER THAN "RegulatoryRecord activation" MIGHT SOUND
# The Task 14 audit found THREE independent mechanisms that can set
# EMA_Status/WHO_Status/ESCOP_Status on an evidence row, with wildly
# different reliability — a naive text-keyword match in
# evidence_extractor.py (confirmed false-positive-prone: "ema" matches
# "schema"/"enema"), an LLM's own subjective "ema_relevance" judgment
# in evidence_standardizer.py, and the real ema_regulatory_connector.py
# (which fetches EMA's actual HMPC inventory PDF and sets a real
# Source_URL/Source_Organization/Evidence_Level). Only the third
# mechanism is safe to build a RegulatoryRecord from, and it is only
# reliably distinguishable from the other two by Source_Type=="Regulatory"
# (confirmed: only the EMA connector path sets this exact value) — so
# THAT is the gate this function enforces, not any text/keyword
# inspection of its own.
#
# Even the real connector's WHO_Status/ESCOP_Status fields are non-
# answers by its own design (literally the string "See source PDF
# (column not reliably text-extractable)" — ema_regulatory_connector.py)
# — this function never reads them, and never constructs a WHO- or
# ESCOP-labeled record from any row, for any reason.
# ======================================================================

# Evidence_Level -> MarketVerificationStatus, for rows that already
# passed the Source_Type=="Regulatory" eligibility gate. Phase 2A —
# this now goes through the SAME classify_ema_hmpc_signal() rule
# _market_status() uses (via CANONICAL_EMA_SIGNAL_TO_MARKET_STATUS
# above), rather than an independently-maintained exact-string dict.
# Verified against the three genuine, hand-verified strings
# ema_regulatory_connector.py's search_regulatory_sources_real() (the
# only production write path to a Source_Type=="Regulatory" row)
# actually emits — "Listed in official EMA HMPC inventory" (->
# inventory_listed, via the "hmpc inventory" structural match),
# "Checked, not found" (-> searched_not_found, via the "not found"
# match), "Not available" (-> source_unavailable) — each still resolves
# to exactly the same MarketVerificationStatus member as before this
# change; see test_classify_ema_hmpc_signal_generic_matrix and
# test_task14_1_regulatory_record_activation.py for the regression
# coverage locking this equivalence in.


def build_regulatory_record(record: Mapping[str, Any]) -> Optional[RegulatoryRecord]:
    """Task 14.1 — adapts an active evidence_records row into a
    data_contracts.RegulatoryRecord, ONLY for rows that are genuinely
    regulatory-connector output, never for an ordinary scientific
    article, an LLM's relevance guess, or a keyword mention.

    ELIGIBILITY GATE (return None otherwise): the row's normalized
    Source_Type must equal "regulatory" (case-insensitive) exactly.
    This is a structural gate, not a content inspection — it does NOT
    look at EMA_Status/WHO_Status/ESCOP_Status/Novel_Food_Status, does
    NOT scan Notes/text for keywords, and does NOT consult any LLM
    field. A PubMed article that mentions "EMA" (or "schema"/"enema" —
    the confirmed evidence_extractor.py substring-match bug this
    function deliberately does not inherit), that has
    EMA_Status=="Yes", or whose LLM-derived ema_relevance says "yes",
    still returns None here unless Source_Type is genuinely
    "Regulatory".

    IDENTITY REQUIREMENT: a normalized Evidence_Record_ID (or lowercase
    evidence_record_id alias) must exist, via normalize_missing_value()
    (the same helper every prior activation in this module already
    uses — not reimplemented here). No stable ID -> None.

    MAPPINGS (see module-level docstring above and the Task 14 audit
    for the full reasoning):
      - status: from Evidence_Level, via classify_ema_hmpc_signal()
        (Phase 2A shared helper) then CANONICAL_EMA_SIGNAL_TO_MARKET_STATUS;
        anything unrecognized -> UNKNOWN. NEVER REGULATORY_MONOGRAPH_EXISTS
        for inventory presence — being listed in an assessment inventory
        is not the same claim as having a published monograph.
      - jurisdiction_or_market: from Target_Market, verbatim.
      - monograph_source: the literal string "EMA/HMPC", but ONLY when
        Source_Organization also identifies the EMA/HMPC connector —
        a strict normalized-prefix check (startswith "ema hmpc",
        case-insensitive), matching the real connector's actual
        organization strings only, NOT a loose substring/"contains
        ema" check (which would also match, e.g., an organization
        named "Schema Regulatory Authority", or one that merely
        mentions EMA mid-sentence) — otherwise None. This is
        deliberately a second, independent check on top of the
        Source_Type gate, not redundant with it: Source_Type==
        "Regulatory" alone does not guarantee this particular row is
        EMA-sourced if some other regulatory connector existed in the
        future.
      - source_record_ids: exactly one entry, the normalized
        Evidence_Record_ID.

    ALWAYS LEFT NONE, NEVER POPULATED FROM ANYTHING:
      - scope_whole_herb_or_extract, scope_traditional_indication,
        scope_dosage_form — no source in the active schema carries a
        regulatory DOCUMENT's own stated scope; populating these from
        candidate-level indication/dosage-form/plant-part values would
        fabricate a claim the source document never made.
      - last_verified_date — Source_Year is a document/PDF snapshot
        year (e.g. "2021"), not a verification date; converting it to
        a fabricated full date would overstate currency.

    NOT ON THIS CONTRACT AT ALL: no Source_URL/DOI field is added or
    duplicated here — the evidence record referenced by
    source_record_ids remains the one authoritative place that URL
    lives (evidence_records.source_url, already reachable via
    ScientificEvidence.doi_pmid_url for the same row).

    Never mutates `record`. Never raises — any unexpected shape
    produces None, the same fail-safe-not-fail-open discipline as the
    other builders in this module.
    """
    try:
        source_type = normalize_missing_value(record.get("Source_Type"))
        if source_type is None or str(source_type).strip().lower() != "regulatory":
            return None

        evidence_record_id = normalize_missing_value(record.get("Evidence_Record_ID"))
        if evidence_record_id is None:
            evidence_record_id = normalize_missing_value(record.get("evidence_record_id"))
        if evidence_record_id is None:
            return None

        evidence_level = normalize_missing_value(record.get("Evidence_Level"))
        status = MarketVerificationStatus.UNKNOWN
        if evidence_level is not None:
            status = CANONICAL_EMA_SIGNAL_TO_MARKET_STATUS.get(
                classify_ema_hmpc_signal(evidence_level), MarketVerificationStatus.UNKNOWN
            )

        jurisdiction_or_market = normalize_missing_value(record.get("Target_Market"))

        source_organization = normalize_missing_value(record.get("Source_Organization"))
        monograph_source = None
        if source_organization is not None:
            # Task 14.1 correction — narrowly matches the real EMA
            # connector's actual organization strings only:
            #   "EMA HMPC — Inventory of herbal substances for assessment"
            #   "EMA HMPC (live fetch failed)"
            #   "EMA HMPC (lookup unavailable)"
            # (ema_regulatory_connector.py / regulatory_connector.py,
            # confirmed by direct inspection — every real value begins
            # with exactly "EMA HMPC"). Deliberately a strict
            # normalized-prefix check, NOT a substring/contains check:
            # "ema" anywhere in the string (e.g. an organization named
            # "Schema Regulatory Authority", or one that merely
            # mentions EMA mid-sentence) must NOT match — only genuine
            # EMA/HMPC connector output starts this way.
            normalized_org = str(source_organization).strip().lower()
            if normalized_org.startswith("ema hmpc"):
                monograph_source = "EMA/HMPC"

        return RegulatoryRecord(
            status=status,
            jurisdiction_or_market=jurisdiction_or_market,
            monograph_source=monograph_source,
            source_record_ids=[str(evidence_record_id)],
            # Deliberately always None — see docstring above.
            scope_whole_herb_or_extract=None,
            scope_traditional_indication=None,
            scope_dosage_form=None,
            last_verified_date=None,
        )
    except Exception:
        # Malformed input must degrade to "no record produced," never
        # raise — same discipline as every other builder in this module.
        return None


# ===========================================================================
# Phase 5 — evaluate_applicability(): evidence-vs-target-context
# applicability contract. A THIRD, separate applicability signal, distinct
# from both Direct_For_Selected_Product (module top) and
# Applicability_Classification/build_standard_evidence() above (Task 10.2,
# indication+dosage_form-only). This one compares an evidence record's own
# attributes against an EXPLICIT target-product/session context — no value
# is ever judged in isolation (addendum §3.4). Weights/thresholds are
# imported from phase5_scoring_config.py, never re-declared here.
# ===========================================================================

from phase5_scoring_config import (
    MATCH as _APPL_MATCH,
    PARTIAL as _APPL_PARTIAL,
    UNKNOWN as _APPL_UNKNOWN,
    MISMATCH as _APPL_MISMATCH,
    NOT_APPLICABLE as _APPL_NOT_APPLICABLE,
    APPLICABILITY_FACTORS,
    APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE,
    APPLICABILITY_CLASSIFICATION_WHEN_NOTHING_EVALUABLE,
    APPLICABILITY_COMPLETENESS_WHEN_NOTHING_EVALUABLE,
    APPLICABILITY_CLASSIFICATION_PRECEDENCE,
    APPLICABILITY_DIMENSIONS,
)
from general_indication_relevance import (
    MATCH_NO_MATCH as _INDICATION_MATCH_NO_MATCH,
)


# ---------------------------------------------------------------------------
# Preparation-transferability helpers.  These live beside the authoritative
# evaluate_applicability() contract so extraction, candidate discovery and the
# final decision path all normalize the same concepts instead of maintaining
# parallel preparation vocabularies.  The helpers only normalize facts that
# are explicitly present; they never infer an unreported preparation, route or
# dose from a selected product.
# ---------------------------------------------------------------------------
_PREPARATION_CATEGORY_PATTERNS = (
    ("essential_oil", ("essential oil", "volatile oil")),
    ("hydroalcoholic", ("hydroalcoholic", "hydroethanolic", "ethanol-water", "ethanol water")),
    ("ethanolic", ("ethanolic extract", "ethanol extract")),
    ("aqueous", ("aqueous extract", "water extract", "aqueous infusion", "infusion", "decoction", "herbal tea", "tisane", "tea")),
    ("dry_extract", ("standardized dry extract", "standardised dry extract", "dry extract")),
    ("tincture", ("tincture",)),
    ("powder", ("powder", "powdered herb", "powdered herbal")),
    ("juice", ("fresh juice", "expressed juice", "juice")),
)


def preparation_category_from_text(value: Any) -> str:
    """Return a conservative canonical category for an EXPLICIT preparation.

    This is vocabulary normalization, not similarity inference.  Generic words
    such as ``extract`` or dosage-form-only words such as ``capsule`` are left
    uncategorized because they do not establish how the botanical material was
    prepared.
    """
    if _appl_is_blank(value):
        return ""
    text = _appl_norm(value)
    for category, terms in _PREPARATION_CATEGORY_PATTERNS:
        if any(term in text for term in terms):
            return category
    return ""


def preparation_from_product_form(value: Any) -> str:
    """Use a product-form string as Target_Preparation only when it itself
    names a botanical preparation (infusion/tincture/extract/oil/powder/etc.).

    A capsule/tablet/softgel is a dosage form, not a preparation; returning an
    empty string for those prevents the platform from silently treating a
    capsule containing an unspecified powder as equivalent to a standardized
    extract studied in a trial.
    """
    if _appl_is_blank(value):
        return ""
    text = str(value).strip()
    category = preparation_category_from_text(text)
    return text if category else ""




def canonical_plant_part(value: Any) -> str:
    """Normalize only unambiguous botanical-part spelling/plural variants."""
    if _appl_is_blank(value):
        return ""
    text = _appl_norm(value).replace("-", " ")
    aliases = {
        "leaf": "leaf", "leaves": "leaf",
        "root": "root", "roots": "root",
        "flower": "flower", "flowers": "flower",
        "seed": "seed", "seeds": "seed",
        "fruit": "fruit", "fruits": "fruit", "berry": "fruit", "berries": "fruit",
        "rhizome": "rhizome", "rhizomes": "rhizome",
        "stem": "stem", "stems": "stem",
        "bark": "bark",
        "aerial part": "aerial part", "aerial parts": "aerial part",
    }
    return aliases.get(text, text)


def canonical_administration_route(value: Any) -> str:
    """Normalize unambiguous route wording without inferring an unreported route."""
    if _appl_is_blank(value):
        return ""
    text = _appl_norm(value).replace("-", " ")
    aliases = {
        "oral": "oral", "orally": "oral", "by mouth": "oral",
        "topical": "topical", "topically": "topical", "dermal": "topical",
        "inhalation": "inhalation", "inhaled": "inhalation",
        "mucosal": "mucosal", "oromucosal": "mucosal", "buccal": "mucosal",
        "injection": "injection", "intravenous": "injection",
        "intramuscular": "injection", "subcutaneous": "injection",
    }
    return aliases.get(text, text)

def parse_dose_value_unit(value: Any) -> tuple[Optional[float], str]:
    """Parse one explicit human-readable dose into numeric value + unit.

    Only simple absolute dose expressions are accepted (e.g. ``240 mg/day``,
    ``300 mg daily``, ``2 g``).  Concentrations, ranges and ambiguous numbers
    deliberately return ``(None, "")`` rather than inventing comparability.
    """
    if _appl_is_blank(value):
        return None, ""
    import re as _re
    text = str(value).strip().lower().replace("μ", "µ")
    # Ranges require a target-range model rather than choosing one endpoint.
    if _re.search(r"\d\s*(?:-|–|—|to)\s*\d", text):
        return None, ""
    m = _re.search(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*(µg|ug|mcg|mg|g|ml|mL)"
        r"(?:\s*(?:/|per\s+)(day|d|24\s*h|kg(?:/day|/d)?))?\b",
        text, flags=_re.IGNORECASE,
    )
    if not m:
        return None, ""
    try:
        number = float(m.group(1))
    except (TypeError, ValueError):
        return None, ""
    unit = m.group(2).lower().replace("ug", "µg").replace("mcg", "µg")
    denominator = (m.group(3) or "").lower().replace(" ", "")
    if denominator in {"d", "24h"}:
        denominator = "day"
    if denominator:
        unit = f"{unit}/{denominator}"
    elif _re.search(r"\b(?:daily|per day|each day)\b", text):
        unit = f"{unit}/day"
    return number, unit


def build_transferability_target_context(
    indication: str = "",
    dosage_form: str = "",
    standardized_project: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build the one authoritative target-product context used by Phase 5.

    Missing product facts stay missing.  ``Required_Transferability_Dimensions``
    marks the dimensions that must be known before the platform may call
    transferability complete; evaluate_applicability() converts an omitted
    required target fact into UNKNOWN rather than quietly ignoring it.
    """
    project = dict(standardized_project or {})
    context: dict[str, Any] = {}

    target_indication = (
        project.get("target_indication") or project.get("Target_Indication") or indication
    )
    if not _appl_is_blank(target_indication):
        context["Target_Indication"] = target_indication

    target_route = project.get("route") or project.get("target_route") or project.get("Target_Route")
    if not _appl_is_blank(target_route):
        context["Target_Route"] = canonical_administration_route(target_route)

    target_part = (
        project.get("target_plant_part") or project.get("plant_part") or project.get("Target_Plant_Part")
    )
    if not _appl_is_blank(target_part):
        context["Target_Plant_Part"] = canonical_plant_part(target_part)

    explicit_prep = (
        project.get("target_preparation") or project.get("preparation") or project.get("Target_Preparation")
    )
    target_preparation = explicit_prep or preparation_from_product_form(
        project.get("dosage_form") or dosage_form
    )
    if not _appl_is_blank(target_preparation):
        context["Target_Preparation"] = target_preparation
        category = (
            project.get("target_preparation_category")
            or project.get("Target_Preparation_Category")
            or preparation_category_from_text(target_preparation)
        )
        if category:
            context["Target_Preparation_Category"] = category

    # Support future structured UI fields without requiring a new UI now.
    target_min = project.get("target_dose_min", project.get("Target_Dose_Min"))
    target_max = project.get("target_dose_max", project.get("Target_Dose_Max"))
    target_unit = project.get("target_dose_unit", project.get("Target_Dose_Unit"))
    dose_text = project.get("target_dose") or project.get("dose")
    if target_min is None and target_max is None and not _appl_is_blank(dose_text):
        parsed_value, parsed_unit = parse_dose_value_unit(dose_text)
        if parsed_value is not None:
            target_min = target_max = parsed_value
            target_unit = target_unit or parsed_unit
    if target_min is not None:
        context["Target_Dose_Min"] = target_min
    if target_max is not None:
        context["Target_Dose_Max"] = target_max
    if not _appl_is_blank(target_unit):
        context["Target_Dose_Unit"] = target_unit

    # These are the clinically material transferability dimensions for a
    # product decision.  If the product definition has not specified one, the
    # result is explicitly incomplete/UNKNOWN, not a full MATCH. Species is
    # intentionally excluded: candidate identity is already enforced upstream.
    context["Required_Transferability_Dimensions"] = (
        "plant_part", "preparation", "route", "dose", "indication"
    )
    return context


def evidence_transferability_fields(
    *,
    species: Any = "",
    plant_part: Any = "",
    preparation: Any = "",
    route: Any = "",
    dose: Any = "",
    indication_match_type: Any = "",
) -> dict[str, Any]:
    """Map explicit record facts to evaluate_applicability()'s Evidence_* shape."""
    dose_value, dose_unit = parse_dose_value_unit(dose)
    out: dict[str, Any] = {
        "Evidence_Species": species or "",
        "Evidence_Plant_Part": canonical_plant_part(plant_part),
        "Evidence_Preparation": preparation or "",
        "Evidence_Preparation_Category": preparation_category_from_text(preparation),
        "Evidence_Route": canonical_administration_route(route),
        "Indication_Match_Type": indication_match_type or "",
    }
    if dose_value is not None:
        out["Evidence_Dose"] = dose_value
        out["Evidence_Dose_Unit"] = dose_unit
    return out


def _appl_is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _appl_norm(value) -> str:
    return str(value).strip().lower()


def _appl_dimension_simple(evidence_value, target_value) -> str:
    """MATCH/MISMATCH/UNKNOWN/NOT_APPLICABLE for a plain-equality
    dimension (species, plant_part, route) — no PARTIAL support in this
    phase (addendum §3.4/correction round 6 item 5)."""
    if _appl_is_blank(target_value):
        return _APPL_NOT_APPLICABLE
    if _appl_is_blank(evidence_value):
        return _APPL_UNKNOWN
    return _APPL_MATCH if _appl_norm(evidence_value) == _appl_norm(target_value) else _APPL_MISMATCH


def _appl_dimension_preparation(evidence_row: Mapping[str, Any], target_context: Mapping[str, Any]) -> str:
    """Deterministic parent-category rule (addendum §3.4, FINAL per
    correction round 6): exact canonical value match -> MATCH; different
    specific value but explicit, matching parent category -> PARTIAL;
    explicit, differing parent categories -> MISMATCH; either side
    missing what's needed -> UNKNOWN. Never inferred from free-text
    similarity between the specific preparation names themselves.

    When the target cares about category (supplies Target_Preparation_
    Category) but the evidence side cannot answer that comparison, the
    result is UNKNOWN, not an assumed MISMATCH -- resolving PARTIAL vs.
    MISMATCH genuinely requires both sides' category. When the target
    never mentions category at all, a plain value mismatch is a
    straightforward MISMATCH (no category comparison was ever asked for).

    LEGACY ADAPTER: when the row has no Evidence_Preparation field at
    all, this reuses the pre-existing Preparation_Applicability /
    Dosage_Form_Compatibility signal (main audit §3.2 — already computed
    by _dosage_compatibility()/_preparation_applicability_row() for
    every row) as a direct MATCH/MISMATCH/UNKNOWN result — the same
    reasoning as the dosage_form/Extraction_Method adapter above, so a
    legacy-vocabulary row that already says "Compatible" is not
    penalized to UNKNOWN merely for predating the Evidence_Preparation
    field."""
    target_value = target_context.get("Target_Preparation")
    target_category = target_context.get("Target_Preparation_Category")
    if _appl_is_blank(target_value) and _appl_is_blank(target_category):
        return _APPL_NOT_APPLICABLE

    evidence_value = evidence_row.get("Evidence_Preparation")
    evidence_category = evidence_row.get("Evidence_Preparation_Category")

    value_pair_present = not _appl_is_blank(target_value) and not _appl_is_blank(evidence_value)
    if value_pair_present and _appl_norm(target_value) == _appl_norm(evidence_value):
        return _APPL_MATCH

    if not _appl_is_blank(target_category):
        if _appl_is_blank(evidence_category):
            return _APPL_UNKNOWN
        return _APPL_PARTIAL if _appl_norm(target_category) == _appl_norm(evidence_category) else _APPL_MISMATCH

    if value_pair_present:
        # Values are known to differ (the MATCH check above already
        # failed) and the target never asked about category.
        return _APPL_MISMATCH

    if _appl_is_blank(evidence_value):
        legacy_signal = evidence_row.get("Preparation_Applicability")
        if _appl_is_blank(legacy_signal):
            legacy_signal = evidence_row.get("Dosage_Form_Compatibility")
        if not _appl_is_blank(legacy_signal):
            normalized_legacy = _appl_norm(legacy_signal)
            if normalized_legacy == "compatible":
                return _APPL_MATCH
            if normalized_legacy == "mismatch":
                return _APPL_MISMATCH
            # "Unknown" / "Not evaluated" / anything else recognized but
            # inconclusive -> UNKNOWN, same as the primary contract's
            # own missing-data behavior.

    return _APPL_UNKNOWN


def _appl_dimension_dose(evidence_row: Mapping[str, Any], target_context: Mapping[str, Any]) -> str:
    """Target side is a range (Target_Dose_Min/Max/Unit); evidence side
    must report a COMPARABLE, matching unit before any numeric
    comparison is attempted. No unit conversion, pharmacokinetic
    equivalence, or clinical dose validation (addendum §3.4). Missing or
    incompatible units -> UNKNOWN, never an invented comparison."""
    target_min = target_context.get("Target_Dose_Min")
    target_max = target_context.get("Target_Dose_Max")
    target_unit = target_context.get("Target_Dose_Unit")
    if target_min is None and target_max is None and _appl_is_blank(target_unit):
        return _APPL_NOT_APPLICABLE

    evidence_value = evidence_row.get("Evidence_Dose")
    evidence_unit = evidence_row.get("Evidence_Dose_Unit")
    if evidence_value is None or _appl_is_blank(evidence_unit) or _appl_is_blank(target_unit):
        return _APPL_UNKNOWN
    if _appl_norm(evidence_unit) != _appl_norm(target_unit):
        return _APPL_UNKNOWN
    try:
        value = float(evidence_value)
    except (TypeError, ValueError):
        return _APPL_UNKNOWN
    lo = float(target_min) if target_min is not None else float("-inf")
    hi = float(target_max) if target_max is not None else float("inf")
    return _APPL_MATCH if lo <= value <= hi else _APPL_MISMATCH


def _appl_dimension_indication(evidence_row: Mapping[str, Any], target_context: Mapping[str, Any]) -> str:
    """Reuses the already-authoritative Indication_Match_Type field
    (produced upstream by general_indication_relevance.py via
    indication_candidate_discovery.py, addendum §3.1) — never
    re-classifies indication relevance itself here."""
    target_value = target_context.get("Target_Indication")
    if _appl_is_blank(target_value):
        return _APPL_NOT_APPLICABLE
    match_type = evidence_row.get("Indication_Match_Type")
    if _appl_is_blank(match_type):
        return _APPL_UNKNOWN
    if str(match_type).strip() == _INDICATION_MATCH_NO_MATCH:
        return _APPL_MISMATCH
    return _APPL_MATCH


def evaluate_applicability(
    evidence_row: Mapping[str, Any],
    target_context: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Phase 5 — compare one evidence record's attributes against an
    EXPLICIT target-product/session context, dimension by dimension.
    Never classifies a raw value in isolation (addendum §3.4).

    Returns a dict with:
      Dimension_Status: {dimension: MATCH|PARTIAL|MISMATCH|UNKNOWN|NOT_APPLICABLE, ...}
      Applicability_Classification: worst-status-wins summary label
      Record_Applicability_Factor: min() over evaluable (non-NOT_APPLICABLE) dimensions
      Applicability_Factor: alias of Record_Applicability_Factor (backward compat)
      Applicability_Data_Completeness: "complete" | "incomplete" | "preliminary"

    PROVISIONAL. NOT CLINICALLY VALIDATED. NOT STATISTICALLY CALIBRATED.
    """
    if not target_context:
        dimension_status = {dim: _APPL_NOT_APPLICABLE for dim in APPLICABILITY_DIMENSIONS}
        return {
            "Dimension_Status": dimension_status,
            "Applicability_Classification": APPLICABILITY_CLASSIFICATION_WHEN_NOTHING_EVALUABLE,
            "Record_Applicability_Factor": APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE,
            "Applicability_Factor": APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE,
            "Applicability_Data_Completeness": "preliminary",
        }

    dimension_status = {
        "species": _appl_dimension_simple(
            evidence_row.get("Evidence_Species"), target_context.get("Target_Species")
        ),
        "plant_part": _appl_dimension_simple(
            evidence_row.get("Evidence_Plant_Part"), target_context.get("Target_Plant_Part")
        ),
        "preparation": _appl_dimension_preparation(evidence_row, target_context),
        "route": _appl_dimension_simple(
            evidence_row.get("Evidence_Route"), target_context.get("Target_Route")
        ),
        "dose": _appl_dimension_dose(evidence_row, target_context),
        "indication": _appl_dimension_indication(evidence_row, target_context),
    }

    # Production transferability contexts explicitly identify clinically
    # material dimensions that must be known before a record may be called a
    # complete MATCH.  If the target product itself has not specified one of
    # those dimensions, the older implementation returned NOT_APPLICABLE and
    # silently ignored it, allowing indication+preparation alone to become a
    # misleading full match.  Required-but-unspecified is uncertainty, not
    # irrelevance, so convert only those dimensions to UNKNOWN.  Legacy callers
    # that do not provide Required_Transferability_Dimensions retain their
    # historical behavior unchanged.
    required_dimensions = set(target_context.get("Required_Transferability_Dimensions") or ())
    for dim in required_dimensions:
        if dim in dimension_status and dimension_status[dim] == _APPL_NOT_APPLICABLE:
            dimension_status[dim] = _APPL_UNKNOWN

    evaluable = {
        dim: status for dim, status in dimension_status.items() if status != _APPL_NOT_APPLICABLE
    }

    if not evaluable:
        return {
            "Dimension_Status": dimension_status,
            "Applicability_Classification": APPLICABILITY_CLASSIFICATION_WHEN_NOTHING_EVALUABLE,
            "Record_Applicability_Factor": APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE,
            "Applicability_Factor": APPLICABILITY_FACTOR_WHEN_NOTHING_EVALUABLE,
            "Applicability_Data_Completeness": APPLICABILITY_COMPLETENESS_WHEN_NOTHING_EVALUABLE,
        }

    record_factor = min(APPLICABILITY_FACTORS[status] for status in evaluable.values())

    classification = _APPL_NOT_APPLICABLE
    for candidate_status in APPLICABILITY_CLASSIFICATION_PRECEDENCE:
        if candidate_status in evaluable.values():
            classification = candidate_status
            break

    completeness = "incomplete" if _APPL_UNKNOWN in evaluable.values() else "complete"

    return {
        "Dimension_Status": dimension_status,
        "Applicability_Classification": classification,
        "Record_Applicability_Factor": record_factor,
        "Applicability_Factor": record_factor,
        "Applicability_Data_Completeness": completeness,
    }
