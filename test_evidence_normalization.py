"""Tests for evidence_normalization.py (IMPLEMENTATION_PLAN.md Phase 5)."""

from evidence_normalization import (
    normalize_evidence_record,
    VERIFICATION_VERIFIED,
    VERIFICATION_UNVERIFIED,
    VERIFICATION_MISSING,
    NORMALIZED_FIELD_NAMES,
)


def test_normalizes_all_fourteen_required_fields():
    row = {"Scientific_Name": "Valeriana officinalis"}
    result = normalize_evidence_record(row)
    assert set(result.keys()) == set(NORMALIZED_FIELD_NAMES)
    assert len(result) == 15


def test_every_field_carries_full_provenance():
    row = {"Scientific_Name": "Valeriana officinalis", "Dosage_Form": "Infusion"}
    result = normalize_evidence_record(row)
    for field_name, normalized in result.items():
        d = normalized.to_dict()
        assert set(d.keys()) == {
            "raw_value", "normalized_value", "source_field",
            "extraction_method", "extraction_confidence", "verification_status",
        }


# --- Missing-field handling: values stay missing, never guessed -----------

def test_missing_fields_are_marked_missing_not_guessed():
    row = {}
    result = normalize_evidence_record(row)
    for field_name, normalized in result.items():
        assert normalized.verification_status == VERIFICATION_MISSING
        assert normalized.normalized_value is None


def test_plant_identity_normalizes_a_real_binomial():
    row = {"Scientific_Name": "valeriana   officinalis"}
    result = normalize_evidence_record(row)
    field = result["plant_identity"]
    assert field.normalized_value == "Valeriana officinalis"
    assert field.verification_status == VERIFICATION_VERIFIED
    assert field.source_field == "Scientific_Name"


def test_dosage_form_structured_field_takes_precedence_over_text():
    row = {"Dosage_Form": "Capsule", "Notes": "prepared as an infusion for the trial"}
    result = normalize_evidence_record(row)
    field = result["dosage_form"]
    assert field.normalized_value == "capsule"
    assert field.verification_status == VERIFICATION_VERIFIED
    assert field.extraction_method == "structured_field_match"


def test_dosage_form_falls_back_to_text_when_no_structured_field():
    row = {"Notes": "administered as an herbal tea infusion daily"}
    result = normalize_evidence_record(row)
    field = result["dosage_form"]
    assert field.normalized_value == "infusion"
    assert field.verification_status == VERIFICATION_UNVERIFIED
    assert field.extraction_method == "keyword_match_in_text"


def test_identifiers_extracted_from_structured_phase2_fields():
    row = {"PMID": "12345678", "DOI": "10.1234/example.2020"}
    result = normalize_evidence_record(row)
    field = result["identifiers"]
    assert field.normalized_value == {"pmid": "12345678", "doi": "10.1234/example.2020"}
    assert field.verification_status == VERIFICATION_VERIFIED


def test_identifiers_missing_when_nothing_present():
    row = {"Notes": "a general discussion with no identifiers"}
    result = normalize_evidence_record(row)
    assert result["identifiers"].verification_status == VERIFICATION_MISSING


def test_sample_size_regex_extraction_from_free_text():
    row = {"Notes": "a randomized trial with n=84 participants"}
    result = normalize_evidence_record(row)
    field = result["sample_size"]
    assert field.normalized_value == "84"
    assert field.verification_status == VERIFICATION_UNVERIFIED


def test_duration_regex_extraction_from_free_text():
    row = {"Notes": "treatment continued for 8 weeks before assessment"}
    result = normalize_evidence_record(row)
    field = result["duration"]
    assert field.normalized_value == "8 weeks"


def test_study_type_reuses_evidence_hierarchy_classifier_as_fallback():
    row = {"Notes": "a randomized, double-blind, placebo-controlled trial"}
    result = normalize_evidence_record(row)
    field = result["study_type"]
    assert field.verification_status != VERIFICATION_MISSING
    assert field.extraction_method == "evidence_hierarchy_classifier"


# --- Row-order independence: normalization is per-row, order-agnostic -----

def test_normalization_result_is_independent_of_row_processing_order():
    row_a = {"Scientific_Name": "Valeriana officinalis", "PMID": "111"}
    row_b = {"Scientific_Name": "Melissa officinalis", "PMID": "222"}
    forward = [normalize_evidence_record(row_a), normalize_evidence_record(row_b)]
    backward = [normalize_evidence_record(row_b), normalize_evidence_record(row_a)]
    assert forward[0]["plant_identity"].normalized_value == backward[1]["plant_identity"].normalized_value
    assert forward[1]["plant_identity"].normalized_value == backward[0]["plant_identity"].normalized_value


# --- Backward compatibility: an empty/legacy row never crashes ------------

def test_empty_row_never_crashes():
    result = normalize_evidence_record({})
    assert len(result) == 15


def test_unrelated_extra_fields_are_ignored_without_error():
    row = {"Scientific_Name": "Valeriana officinalis", "Some_Future_Field": {"nested": True}}
    result = normalize_evidence_record(row)
    assert result["plant_identity"].normalized_value == "Valeriana officinalis"
