"""Phase 5 (IMPLEMENTATION_PLAN.md) — Evidence Normalization.

WHAT THIS IS
A single, explicit, auditable stage that runs on a raw evidence/candidate
row BEFORE candidate scoring (see indication_candidate_discovery.py's call
order — this module is imported and called there, ahead of the existing
scoring logic, which is UNCHANGED by this phase). For each of the 15
required fields, produces a NormalizedField carrying: raw_value,
normalized_value, source_field, extraction_method, extraction_confidence,
verification_status.

WHAT THIS NEVER DOES
Every normalize_* function below reads ONLY values already present on the
row. None of them infer, guess, or fill in a missing scientific fact — a
field with no literal source value gets verification_status="missing" and
normalized_value=None, never a plausible-looking default. This mirrors the
same discipline already established in standard_evidence_builder.py
("Missing data is never inferred — a dimension with no detected value is
recorded as missing, never guessed at or defaulted to a match") and
candidate_shortlisting.py's indication-relevance gate.

WHY A NEW MODULE, NOT AN EXTENSION OF evidence_extractor.py
evidence_extractor.py's extract_evidence_from_text() runs once, at Step 2
ingestion time, and its output fields are shaped for that pipeline
(Detected_Dosage_Forms, Publication_Type, etc. — categorical flags, not a
provenance-carrying record per field). Phase 5 needs a distinct, reusable
unit — one NormalizedField per required field, with confidence and
verification status attached — that Evidence Validation (evidence_validation.py)
and any future consumer can inspect per-field, not just read a flat dict.
Where the same literal signal already exists on the row (e.g. Evidence_Level,
Study_Model, PMID — Phase 2), this module reads it rather than re-deriving
it from raw text a second time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

VERIFICATION_VERIFIED = "verified"       # a literal, unambiguous source value
VERIFICATION_UNVERIFIED = "unverified"   # a weaker/heuristic literal match
VERIFICATION_MISSING = "missing"         # genuinely absent on the row — never guessed

NORMALIZED_FIELD_NAMES = (
    "plant_identity", "plant_part", "preparation_extraction_method",
    "administration_route", "dosage_form", "indication", "study_type",
    "study_model", "population", "comparator", "outcome", "result_direction",
    "identifiers", "duration", "sample_size",
)


@dataclass
class NormalizedField:
    raw_value: Any
    normalized_value: Optional[Any]
    source_field: Optional[str]
    extraction_method: str
    extraction_confidence: float
    verification_status: str

    def to_dict(self) -> dict:
        return {
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "source_field": self.source_field,
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
            "verification_status": self.verification_status,
        }


def _missing() -> NormalizedField:
    return NormalizedField(None, None, None, "none", 0.0, VERIFICATION_MISSING)


def _is_present(value) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return text != "" and text.lower() not in ("nan", "none", "null", "unknown")


def _first_present(row: dict, candidates: list[str]):
    for name in candidates:
        value = row.get(name)
        if _is_present(value):
            return name, value
    return None, None


def _keyword_field(row: dict, source_fields: list[str], vocabulary: dict[str, tuple[str, ...]],
                    text_fields: list[str] = None):
    """Shared helper for controlled-vocabulary fields (dosage form,
    administration route, study model, ...). Checks explicit structured
    fields first (verified — the connector/extractor already classified
    it), then falls back to literal keyword matching against free text
    (unverified — a heuristic literal match, not an inference of a fact
    the text doesn't state)."""
    source_field, raw = _first_present(row, source_fields)
    if raw is not None:
        raw_norm = str(raw).strip().lower()
        for canonical, keywords in vocabulary.items():
            if any(k in raw_norm for k in keywords):
                return NormalizedField(raw, canonical, source_field, "structured_field_match", 0.95, VERIFICATION_VERIFIED)
        # A structured field was present but didn't match the known
        # vocabulary — the raw value itself is the most honest normalized
        # value (not fabricated as one of the known categories).
        return NormalizedField(raw, str(raw).strip(), source_field, "structured_field_passthrough", 0.6, VERIFICATION_UNVERIFIED)

    if text_fields:
        blob_field, blob = _first_present(row, text_fields)
        if blob is not None:
            blob_norm = str(blob).strip().lower()
            for canonical, keywords in vocabulary.items():
                if any(k in blob_norm for k in keywords):
                    return NormalizedField(blob, canonical, blob_field, "keyword_match_in_text", 0.5, VERIFICATION_UNVERIFIED)

    return _missing()


# --- Individual field normalizers ------------------------------------------

def normalize_plant_identity(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Scientific_Name", "Alternative_Plant", "Plant"])
    if raw is None:
        return _missing()
    text = re.sub(r"\s+", " ", str(raw).strip())
    parts = text.split(" ")
    if len(parts) >= 2 and parts[0].isalpha():
        normalized = parts[0].capitalize() + " " + " ".join(p.lower() for p in parts[1:])
        confidence, status = 0.9, VERIFICATION_VERIFIED
    else:
        # Not a two-part binomial (e.g. a common name, or a genus-only
        # value) — normalized to consistent casing only, never expanded
        # or guessed into a full scientific name.
        normalized = text
        confidence, status = 0.5, VERIFICATION_UNVERIFIED
    return NormalizedField(raw, normalized, source_field, "literal_string_normalization", confidence, status)


def normalize_plant_part(row: dict) -> NormalizedField:
    vocabulary = {
        "root": ("root",), "leaf": ("leaf", "leaves"), "flower": ("flower",),
        "seed": ("seed",), "bark": ("bark",), "rhizome": ("rhizome",),
        "fruit": ("fruit", "berry"), "whole plant": ("whole plant", "aerial part"),
        "stem": ("stem",),
    }
    return _keyword_field(
        row, ["Alternative_Plant_Part", "Plant_Part", "plant_part"], vocabulary,
        text_fields=["Notes", "Scientific_Rationale"],
    )


def normalize_preparation_extraction_method(row: dict) -> NormalizedField:
    vocabulary = {
        "aqueous extract": ("aqueous extract", "water extract", "decoction", "infusion"),
        "ethanolic extract": ("ethanolic extract", "ethanol extract", "alcoholic extract"),
        "hydroalcoholic extract": ("hydroalcoholic",),
        "essential oil": ("essential oil", "volatile oil"),
        "dry extract": ("dry extract", "standardized extract", "standardised extract"),
        "powder": ("powder",),
        "tincture": ("tincture",),
    }
    return _keyword_field(
        row, ["Extraction_Method"], vocabulary, text_fields=["Notes", "Scientific_Rationale"],
    )


def normalize_administration_route(row: dict) -> NormalizedField:
    vocabulary = {
        "oral": ("oral", "orally", "by mouth", "ingested", "tea", "infusion", "capsule", "tablet"),
        "topical": ("topical", "cream", "ointment", "gel", "applied to skin"),
        "inhalation": ("inhalation", "inhaled", "aromatherapy", "nasal spray"),
        "oral cavity / mucosal": ("mouthwash", "gargle", "oral rinse", "sublingual"),
        "injection": ("injection", "intravenous", "intraperitoneal"),
    }
    return _keyword_field(
        row, ["Administration_Route"], vocabulary,
        text_fields=["Dosage_Form", "Notes", "Scientific_Rationale"],
    )


def normalize_dosage_form(row: dict) -> NormalizedField:
    vocabulary = {
        "infusion": ("infusion", "tea", "herbal tea", "tisane", "decoction"),
        "capsule": ("capsule",), "tablet": ("tablet",),
        "extract": ("extract",), "essential oil": ("essential oil", "volatile oil"),
        "syrup": ("syrup",), "cream": ("cream", "ointment", "topical"),
        "gel": ("gel",), "mouthwash": ("mouthwash", "gargle", "oral rinse"),
        "spray": ("spray",), "powder": ("powder",),
    }
    return _keyword_field(
        row, ["Dosage_Form", "Detected_Dosage_Forms"], vocabulary,
        text_fields=["Notes"],
    )


def normalize_indication(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Target_Indication", "Detected_Indications"])
    if raw is None:
        return _missing()
    normalized = re.sub(r"\s+", " ", str(raw).strip().lower())
    return NormalizedField(raw, normalized, source_field, "literal_string_normalization", 0.8, VERIFICATION_VERIFIED)


def normalize_study_type(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Evidence_Level", "Study_Type", "Evidence_Hierarchy_Detail"])
    if raw is not None:
        return NormalizedField(raw, str(raw).strip(), source_field, "structured_field_passthrough", 0.85, VERIFICATION_VERIFIED)
    # Fall back to the existing, already-tested hierarchy classifier
    # (evidence_hierarchy_classifier.py) against free text — reused, not
    # re-derived, so this stays consistent with every other caller of it.
    text_field, text = _first_present(row, ["Notes", "Scientific_Rationale"])
    if text is not None:
        try:
            from evidence_hierarchy_classifier import classify_evidence_hierarchy
            hierarchy = classify_evidence_hierarchy(text)
        except Exception:
            hierarchy = None
        if hierarchy:
            return NormalizedField(text, hierarchy, text_field, "evidence_hierarchy_classifier", 0.6, VERIFICATION_UNVERIFIED)
    return _missing()


def normalize_study_model(row: dict) -> NormalizedField:
    vocabulary = {
        "human": ("human", "patient", "subject", "volunteer", "clinical trial", "randomized", "randomised"),
        "animal": ("animal", "rat", "rats", "mouse", "mice", "in vivo"),
        "in vitro / cell": ("in vitro", "cell line", "cell culture", "ex vivo"),
    }
    return _keyword_field(
        row, ["Study_Model"], vocabulary, text_fields=["Notes", "Scientific_Rationale"],
    )


def normalize_population(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Population", "LLM_Population"])
    if raw is None:
        return _missing()
    return NormalizedField(raw, str(raw).strip(), source_field, "structured_field_passthrough", 0.6, VERIFICATION_UNVERIFIED)


def normalize_comparator(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Comparator", "LLM_Comparator"])
    if raw is None:
        return _missing()
    return NormalizedField(raw, str(raw).strip(), source_field, "structured_field_passthrough", 0.6, VERIFICATION_UNVERIFIED)


def normalize_outcome(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Primary_Outcome", "LLM_Main_Outcome"])
    if raw is None:
        return _missing()
    return NormalizedField(raw, str(raw).strip(), source_field, "structured_field_passthrough", 0.7, VERIFICATION_VERIFIED)


def normalize_result_direction(row: dict) -> NormalizedField:
    vocabulary = {
        "positive": ("improved", "reduced", "increased efficacy", "significant improvement", "positive"),
        "negative": ("no significant difference", "no effect", "failed", "null result", "negative"),
        "mixed": ("mixed", "inconclusive", "partial"),
    }
    return _keyword_field(
        row, ["Result_Direction", "LLM_Result_Direction"], vocabulary,
    )


_PMID_RE = re.compile(r"\b(\d{6,9})\b")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s;]+\b")
_NCT_RE = re.compile(r"\bNCT\d{8}\b", re.IGNORECASE)


def normalize_identifiers(row: dict) -> NormalizedField:
    """PMID / DOI / NCT ID — read only from fields already carrying them
    (Phase 2's pmid/doi/nct_id, or Source_Record_IDs/Source_URL literal
    text). Never guessed from an unrelated numeric field."""
    found = {}
    for field_name, pattern, key in (
        ("PMID", _PMID_RE, "pmid"), ("DOI", _DOI_RE, "doi"), ("NCT_ID", _NCT_RE, "nct_id"),
    ):
        source_field, raw = _first_present(row, [field_name])
        if raw is not None:
            found[key] = str(raw).strip()

    if not found:
        source_field, raw = _first_present(row, ["Source_Record_IDs", "Source_URL"])
        if raw is not None:
            text = str(raw)
            pmid_match = _PMID_RE.search(text) if "pubmed" in text.lower() or "pmid" in text.lower() else None
            doi_match = _DOI_RE.search(text)
            nct_match = _NCT_RE.search(text)
            if pmid_match:
                found["pmid"] = pmid_match.group(1)
            if doi_match:
                found["doi"] = doi_match.group(0)
            if nct_match:
                found["nct_id"] = nct_match.group(0).upper()
            if found:
                return NormalizedField(raw, found, source_field, "regex_extraction_from_identifier_text", 0.6, VERIFICATION_UNVERIFIED)
        return _missing()

    return NormalizedField(found, found, "PMID/DOI/NCT_ID", "structured_field_passthrough", 0.95, VERIFICATION_VERIFIED)


_DURATION_RE = re.compile(r"\b(\d+)\s*(day|days|week|weeks|month|months|year|years)\b", re.IGNORECASE)


def normalize_duration(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Duration"])
    if raw is not None:
        return NormalizedField(raw, str(raw).strip(), source_field, "structured_field_passthrough", 0.8, VERIFICATION_VERIFIED)
    text_field, text = _first_present(row, ["Notes", "Scientific_Rationale"])
    if text is not None:
        match = _DURATION_RE.search(str(text))
        if match:
            normalized = f"{match.group(1)} {match.group(2).lower()}"
            return NormalizedField(match.group(0), normalized, text_field, "regex_extraction_from_text", 0.55, VERIFICATION_UNVERIFIED)
    return _missing()


_SAMPLE_SIZE_RE = re.compile(r"\bn\s*=\s*(\d+)\b", re.IGNORECASE)
_SAMPLE_SIZE_PATIENTS_RE = re.compile(r"\b(\d+)\s*(patients|subjects|participants|volunteers)\b", re.IGNORECASE)


def normalize_sample_size(row: dict) -> NormalizedField:
    source_field, raw = _first_present(row, ["Sample_Size", "LLM_Sample_Size"])
    if raw is not None:
        return NormalizedField(raw, str(raw).strip(), source_field, "structured_field_passthrough", 0.85, VERIFICATION_VERIFIED)
    text_field, text = _first_present(row, ["Notes", "Scientific_Rationale"])
    if text is not None:
        text_str = str(text)
        match = _SAMPLE_SIZE_RE.search(text_str) or _SAMPLE_SIZE_PATIENTS_RE.search(text_str)
        if match:
            return NormalizedField(match.group(0), match.group(1), text_field, "regex_extraction_from_text", 0.5, VERIFICATION_UNVERIFIED)
    return _missing()


_NORMALIZERS = {
    "plant_identity": normalize_plant_identity,
    "plant_part": normalize_plant_part,
    "preparation_extraction_method": normalize_preparation_extraction_method,
    "administration_route": normalize_administration_route,
    "dosage_form": normalize_dosage_form,
    "indication": normalize_indication,
    "study_type": normalize_study_type,
    "study_model": normalize_study_model,
    "population": normalize_population,
    "comparator": normalize_comparator,
    "outcome": normalize_outcome,
    "result_direction": normalize_result_direction,
    "identifiers": normalize_identifiers,
    "duration": normalize_duration,
    "sample_size": normalize_sample_size,
}


def normalize_evidence_record(row: dict) -> dict[str, NormalizedField]:
    """The ONE call site for Phase 5 Evidence Normalization. Runs every
    field normalizer above against the same raw row and returns a
    {field_name: NormalizedField} dict — called once per evidence row,
    before evidence_validation.validate_evidence_record() and before any
    scoring."""
    return {name: fn(row) for name, fn in _NORMALIZERS.items()}
