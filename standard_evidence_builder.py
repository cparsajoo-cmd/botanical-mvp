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

from data_contracts import EvidenceApplicability, EvidenceHierarchyLevel, ScientificEvidence

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
    selected_form = str(record.get("Dosage_Form", "")).strip().lower()
    selected_indication = str(record.get("Target_Indication", "")).strip().lower()

    detected_form = (
        str(record.get("Detected_Dosage_Forms", "")) or
        str(record.get("Detected_Dosage_Form", ""))
    ).strip()

    detected_indication = (
        str(record.get("Detected_Indications", "")) or
        str(record.get("Target_Indication_Detected", ""))
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
        "Sample_Size": record.get("LLM_Sample_Size", ""),
        "Comparator": record.get("LLM_Comparator", ""),
        "Primary_Outcome": record.get("LLM_Main_Outcome", ""),
        "Result_Direction": record.get("LLM_Result_Direction", ""),
        "Safety_Signal": record.get("LLM_Safety_Signal", ""),
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
