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

from data_contracts import EvidenceApplicability

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
