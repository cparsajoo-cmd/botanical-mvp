"""Phase 5 (IMPLEMENTATION_PLAN.md) — Evidence Validation.

Runs on an already-normalized evidence row (evidence_normalization.py's
output), AFTER normalization and BEFORE candidate scoring — see
indication_candidate_discovery.py's call order. Produces explicit,
independently-inspectable results for each required check plus one
overall_status. This module computes NO score and changes NO scoring
weight — see IMPLEMENTATION_PLAN.md Phase 5's own constraint; scoring
stays exactly what Phase 3 (candidate_shortlisting.py's Overall_Score)
already computes.

CRITICAL SCIENTIFIC RULES THIS MODULE ENFORCES (see each function's
docstring for which rule it implements):
  - General indication evidence must never be attributed to a plant
    without a plant-specific link.
  - A source URL alone is not enough to establish plant-specific evidence.
  - Mechanistic evidence must not be labeled clinical evidence.
  - Registry records without reported results must not be treated as
    positive efficacy evidence.
  - Duplicate PMID/DOI/NCT records must not increase evidence strength.
  - Missing values remain missing, never guessed.
  - Compound similarity is never used as proof of indication efficacy —
    this module never reads a compound/chemistry field to decide any
    validation result.
"""
from __future__ import annotations

import re
from typing import Optional

from evidence_normalization import NormalizedField, VERIFICATION_MISSING

VALID = "valid"
VALID_WITH_LIMITATIONS = "valid_with_limitations"
REJECTED = "rejected"
NOT_ASSESSABLE = "not_assessable"

REQUIRED_CHECK_NAMES = (
    "plant_identity_resolved", "source_identifier_present",
    "plant_specific_attribution", "indication_relevance",
    "study_type_consistency", "outcome_presence",
    "duplicate_study", "contradictory_or_negative_evidence",
    "preparation_applicability", "missing_critical_fields",
)


def _norm_text(value) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _evidence_text_blob(row: dict) -> str:
    parts = [
        row.get("Notes", ""), row.get("Scientific_Rationale", ""),
        row.get("Applicability_Summary", ""), row.get("Source_Title", ""),
        row.get("Evidence_Source", ""),
    ]
    return " ".join(str(p) for p in parts if p)


# --- Individual checks ------------------------------------------------------

def check_plant_identity_resolved(normalized: dict[str, NormalizedField]) -> dict:
    field = normalized.get("plant_identity")
    resolved = bool(field and field.verification_status != VERIFICATION_MISSING)
    return {"passed": resolved, "detail": "Plant identity present and resolved." if resolved
            else "No plant identity value found on this record."}


def check_source_identifier_present(row: dict, normalized: dict[str, NormalizedField]) -> dict:
    identifiers = normalized.get("identifiers")
    has_identifier = bool(identifiers and identifiers.verification_status != VERIFICATION_MISSING)
    has_url = bool(str(row.get("Source_URL", "")).strip())
    passed = has_identifier or has_url
    return {"passed": passed, "detail": "A source identifier or URL is present." if passed
            else "No PMID/DOI/NCT ID or Source_URL found on this record."}


def check_plant_specific_attribution(row: dict, plant_name: str) -> dict:
    """Rule: general indication evidence must never be attributed to a
    plant without a plant-specific link, and a source URL alone is not
    enough. This check requires the plant's OWN name to appear literally
    in the evidence text itself (title/notes/rationale) — a Source_URL or
    Source_Record_IDs value, on its own, never satisfies this check."""
    plant_tokens = [t for t in _norm_text(plant_name).split() if len(t) >= 4]
    if not plant_tokens:
        return {"passed": False, "detail": "No usable plant name to check attribution against."}
    text = _norm_text(_evidence_text_blob(row))
    if not text:
        return {"passed": False, "detail": "No evidence text available to verify plant-specific mention "
                                            "(Source_URL alone does not establish plant-specific evidence)."}
    matched = any(token in text for token in plant_tokens)
    return {"passed": matched, "detail": "The plant is explicitly named in the evidence text." if matched
            else "The evidence text does not literally mention this plant — "
                 "not attributable as plant-specific evidence."}


def check_indication_relevance(row: dict, indication: str) -> dict:
    indication_tokens = [t for t in _norm_text(indication).split() if len(t) >= 4]
    if not indication_tokens:
        return {"passed": False, "detail": "No indication supplied to check relevance against."}
    text = _norm_text(_evidence_text_blob(row))
    matched = any(token in text for token in indication_tokens)
    return {"passed": matched, "detail": "The evidence text references the requested indication." if matched
            else "The evidence text does not reference the requested indication."}


def check_study_type_consistency(row: dict, normalized: dict[str, NormalizedField]) -> dict:
    """Rule: mechanistic evidence must not be labeled clinical evidence.
    Fails if the study-model signal says in vitro/animal but the claimed
    Evidence_Level/study type text claims clinical/human evidence."""
    study_model = normalized.get("study_model")
    study_type = normalized.get("study_type")
    if not study_model or study_model.verification_status == VERIFICATION_MISSING:
        return {"passed": True, "detail": "No study-model signal to check for a mismatch — not flagged."}

    model_value = _norm_text(study_model.normalized_value)
    claimed = _norm_text(study_type.normalized_value if study_type else row.get("Evidence_Level", ""))
    is_mechanistic_model = model_value in ("animal", "in vitro cell", "in vitro / cell")
    # Word-boundary check: "preclinical" must NOT match "clinical" as a
    # substring (it did before this fix — a real bug this test caught).
    claimed_tokens = set(claimed.split())
    claims_clinical = "clinical" in claimed_tokens or "human" in claimed_tokens
    inconsistent = is_mechanistic_model and claims_clinical
    return {"passed": not inconsistent,
            "detail": "Study type/model are consistent." if not inconsistent
            else f"Inconsistent: study model is '{study_model.normalized_value}' but evidence is "
                 f"labeled '{claimed}' — mechanistic evidence must not be labeled clinical evidence."}


_REGISTRY_SOURCE_MARKERS = ("clinicaltrials gov", "clinical trial registry", "trial registry")


def check_outcome_presence(row: dict, normalized: dict[str, NormalizedField]) -> dict:
    """Rule: registry records without reported results must not be treated
    as positive efficacy evidence."""
    outcome = normalized.get("outcome")
    result_direction = normalized.get("result_direction")
    source_type = _norm_text(row.get("Source_Type", "") or row.get("Evidence_Source", ""))
    is_registry = any(marker in source_type for marker in _REGISTRY_SOURCE_MARKERS)

    has_outcome = bool(outcome and outcome.verification_status != VERIFICATION_MISSING)
    claims_positive = bool(
        result_direction and result_direction.normalized_value == "positive"
    )

    if is_registry and claims_positive and not has_outcome:
        return {"passed": False,
                "detail": "Registry record claims a positive result direction with no reported "
                          "outcome — a registry entry without reported results must not be "
                          "treated as positive efficacy evidence."}
    if not has_outcome:
        return {"passed": False, "detail": "No outcome/result data present on this record."}
    return {"passed": True, "detail": "An outcome is present and, if from a registry, is not "
                                       "an unsupported positive claim."}


def check_duplicate_study(normalized: dict[str, NormalizedField], seen_identifiers: Optional[set]) -> dict:
    """Rule: duplicate PMID/DOI/NCT records must not increase evidence
    strength. seen_identifiers is a mutable set the caller accumulates
    ACROSS a candidate's rows — this function only reports whether THIS
    row's identifiers were already seen; it never removes or scores
    anything itself (that stays the caller's responsibility, unchanged
    from Phase 3)."""
    identifiers_field = normalized.get("identifiers")
    if not identifiers_field or identifiers_field.verification_status == VERIFICATION_MISSING:
        return {"passed": True, "is_duplicate": False, "detail": "No identifiers to check for duplication."}

    ids = identifiers_field.normalized_value or {}
    id_values = {v for v in ids.values() if v}
    if not id_values:
        return {"passed": True, "is_duplicate": False, "detail": "No identifiers to check for duplication."}

    if seen_identifiers is None:
        return {"passed": True, "is_duplicate": False, "detail": "No cross-row duplicate tracking supplied."}

    is_duplicate = bool(id_values & seen_identifiers)
    seen_identifiers.update(id_values)
    return {
        "passed": not is_duplicate, "is_duplicate": is_duplicate,
        "detail": "This record's identifier(s) were already counted for this candidate — "
                  "duplicate, must not increase evidence strength." if is_duplicate
        else "No prior record with the same identifier(s) seen for this candidate.",
    }


def check_contradictory_or_negative_evidence(row: dict) -> dict:
    text = _evidence_text_blob(row)
    try:
        from negative_evidence_classifier import classify_negative_evidence
        result = classify_negative_evidence(text)
        has_negative = bool(result.is_negative)
        detail = (f"Negative/contradictory finding(s) detected: {result.finding_types}" if has_negative
                  else "No negative or contradictory finding detected.")
    except Exception:
        has_negative = bool(row.get("Has_Negative_Evidence"))
        detail = "Has_Negative_Evidence flag is set." if has_negative else "No negative evidence flag set."
    return {"passed": not has_negative, "has_negative_evidence": has_negative, "detail": detail}


def check_preparation_applicability(row: dict, normalized: dict[str, NormalizedField], dosage_form: str) -> dict:
    if not dosage_form:
        return {"passed": True, "detail": "No requested dosage form to check applicability against."}
    detected = normalized.get("dosage_form")
    if not detected or detected.verification_status == VERIFICATION_MISSING:
        return {"passed": True, "detail": "No dosage form detected on this record — not flagged as a mismatch."}
    requested = _norm_text(dosage_form)
    found = _norm_text(detected.normalized_value)
    applicable = requested in found or found in requested
    return {"passed": applicable, "detail": "Detected dosage form matches the requested one." if applicable
            else f"Detected dosage form '{detected.normalized_value}' does not match requested '{dosage_form}'."}


def check_missing_critical_fields(normalized: dict[str, NormalizedField]) -> dict:
    critical = ("plant_identity", "indication", "study_type")
    missing = [name for name in critical if normalized.get(name) is None
               or normalized[name].verification_status == VERIFICATION_MISSING]
    return {"passed": not missing, "missing_fields": missing,
            "detail": "No critical fields missing." if not missing
            else f"Missing critical field(s): {', '.join(missing)}."}


def _derive_overall_status(checks: dict) -> str:
    if not checks["plant_identity_resolved"]["passed"]:
        return NOT_ASSESSABLE
    if not checks["plant_specific_attribution"]["passed"]:
        return REJECTED
    if not checks["indication_relevance"]["passed"]:
        return NOT_ASSESSABLE
    if not checks["study_type_consistency"]["passed"]:
        return REJECTED

    limitations = (
        not checks["source_identifier_present"]["passed"]
        or not checks["outcome_presence"]["passed"]
        or checks["duplicate_study"].get("is_duplicate", False)
        or checks["contradictory_or_negative_evidence"].get("has_negative_evidence", False)
        or not checks["preparation_applicability"]["passed"]
        or not checks["missing_critical_fields"]["passed"]
    )
    return VALID_WITH_LIMITATIONS if limitations else VALID


def validate_evidence_record(
    row: dict,
    *,
    plant_name: str,
    indication: str,
    dosage_form: str = "",
    normalized_fields: dict[str, NormalizedField] = None,
    seen_identifiers: Optional[set] = None,
) -> dict:
    """The ONE call site for Phase 5 Evidence Validation. `normalized_fields`
    should be evidence_normalization.normalize_evidence_record(row)'s
    output — computed once, passed in, never recomputed here.
    `seen_identifiers` is an optional set the CALLER accumulates across a
    candidate's rows to detect duplicate studies (see check_duplicate_study).

    Returns {check_name: result_dict, ..., "overall_status": one of
    valid/valid_with_limitations/rejected/not_assessable}.
    """
    if normalized_fields is None:
        from evidence_normalization import normalize_evidence_record
        normalized_fields = normalize_evidence_record(row)

    checks = {
        "plant_identity_resolved": check_plant_identity_resolved(normalized_fields),
        "source_identifier_present": check_source_identifier_present(row, normalized_fields),
        "plant_specific_attribution": check_plant_specific_attribution(row, plant_name),
        "indication_relevance": check_indication_relevance(row, indication),
        "study_type_consistency": check_study_type_consistency(row, normalized_fields),
        "outcome_presence": check_outcome_presence(row, normalized_fields),
        "duplicate_study": check_duplicate_study(normalized_fields, seen_identifiers),
        "contradictory_or_negative_evidence": check_contradictory_or_negative_evidence(row),
        "preparation_applicability": check_preparation_applicability(row, normalized_fields, dosage_form),
        "missing_critical_fields": check_missing_critical_fields(normalized_fields),
    }
    checks["overall_status"] = _derive_overall_status(checks)
    return checks
