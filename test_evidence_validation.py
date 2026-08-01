"""Tests for evidence_validation.py (IMPLEMENTATION_PLAN.md Phase 5)."""

from evidence_normalization import normalize_evidence_record
from evidence_validation import (
    validate_evidence_record,
    VALID,
    VALID_WITH_LIMITATIONS,
    REJECTED,
    NOT_ASSESSABLE,
)


def _validate(row, plant_name="Valeriana officinalis", indication="sleep", dosage_form="Infusion", seen=None):
    return validate_evidence_record(
        row, plant_name=plant_name, indication=indication, dosage_form=dosage_form,
        seen_identifiers=seen,
    )


# --- Plant-specific attribution / evidence leakage prevention -------------

def test_plant_specific_attribution_passes_when_plant_named_in_text():
    row = {"Notes": "Valeriana officinalis reduced sleep latency in a randomized trial."}
    result = _validate(row)
    assert result["plant_specific_attribution"]["passed"] is True


def test_plant_specific_attribution_fails_when_plant_not_named():
    # THE core leakage-prevention rule: a general indication record must
    # never be attributed to a plant it never mentions.
    row = {"Scientific_Name": "Valeriana officinalis", "Target_Indication": "sleep",
           "Notes": "A general review of herbal approaches to sleep problems."}
    result = _validate(row)
    assert result["plant_specific_attribution"]["passed"] is False
    assert result["overall_status"] == REJECTED


def test_source_url_alone_does_not_establish_plant_specific_evidence():
    # Explicit critical rule: "A source URL alone is not enough."
    row = {"Source_URL": "https://pubmed.ncbi.nlm.nih.gov/99999/", "Notes": ""}
    result = _validate(row)
    assert result["plant_specific_attribution"]["passed"] is False


def test_evidence_leakage_general_indication_text_never_attributed_without_plant_mention():
    row = {"Scientific_Name": "Morus alba", "Target_Indication": "type 2 diabetes",
           "Notes": "Type 2 diabetes and blood glucose review covering many botanicals in general."}
    result = _validate(row, plant_name="Morus alba", indication="type 2 diabetes")
    assert result["plant_specific_attribution"]["passed"] is False
    assert result["overall_status"] == REJECTED


# --- Duplicate-source suppression ------------------------------------------

def test_duplicate_pmid_is_flagged_and_must_not_increase_strength():
    row1 = {"Notes": "Valeriana officinalis improved sleep quality.", "PMID": "12345"}
    row2 = {"Notes": "Valeriana officinalis improved sleep quality (same study, re-listed).", "PMID": "12345"}
    seen = set()
    result1 = _validate(row1, seen=seen)
    result2 = _validate(row2, seen=seen)
    assert result1["duplicate_study"]["is_duplicate"] is False
    assert result2["duplicate_study"]["is_duplicate"] is True
    assert result2["duplicate_study"]["passed"] is False


def test_different_pmid_is_not_flagged_as_duplicate():
    row1 = {"Notes": "Valeriana officinalis improved sleep quality.", "PMID": "111"}
    row2 = {"Notes": "Valeriana officinalis reduced sleep latency.", "PMID": "222"}
    seen = set()
    _validate(row1, seen=seen)
    result2 = _validate(row2, seen=seen)
    assert result2["duplicate_study"]["is_duplicate"] is False


# --- Registry-without-results handling --------------------------------------

def test_registry_record_without_results_is_not_treated_as_positive_efficacy():
    row = {
        "Notes": "Valeriana officinalis sleep study registered on ClinicalTrials.gov.",
        "Source_Type": "ClinicalTrials.gov",
        "Result_Direction": "positive",
        # No Primary_Outcome / LLM_Main_Outcome — a registry stub.
    }
    result = _validate(row)
    assert result["outcome_presence"]["passed"] is False
    assert "registry" in result["outcome_presence"]["detail"].lower()


def test_registry_record_with_reported_outcome_passes():
    row = {
        "Notes": "Valeriana officinalis sleep study on ClinicalTrials.gov with reported results.",
        "Source_Type": "ClinicalTrials.gov",
        "Result_Direction": "positive",
        "Primary_Outcome": "Sleep latency reduced by 12 minutes vs placebo (p<0.05).",
    }
    result = _validate(row)
    assert result["outcome_presence"]["passed"] is True


# --- Mechanistic-vs-clinical classification ---------------------------------

def test_mechanistic_evidence_is_not_accepted_as_clinical():
    row = {
        "Scientific_Name": "Valeriana officinalis", "Target_Indication": "sleep",
        "Notes": "Valeriana officinalis extract tested in vitro on GABA receptor binding assays "
                 "relevant to sleep.",
        "Study_Model": "In vitro",
        "Evidence_Level": "Clinical / human evidence",  # mislabeled — the bug this rule catches
    }
    result = _validate(row)
    assert result["study_type_consistency"]["passed"] is False
    assert result["overall_status"] == REJECTED


def test_correctly_labeled_mechanistic_evidence_passes_consistency_check():
    row = {
        "Scientific_Name": "Valeriana officinalis", "Target_Indication": "sleep",
        "Notes": "Valeriana officinalis extract tested in vitro on GABA receptor binding assays "
                 "relevant to sleep.",
        "Study_Model": "In vitro",
        "Evidence_Level": "Preclinical / mechanistic evidence",
    }
    result = _validate(row)
    assert result["study_type_consistency"]["passed"] is True


def test_correctly_labeled_clinical_evidence_passes_consistency_check():
    row = {
        "Notes": "Valeriana officinalis randomized controlled trial in human patients with insomnia.",
        "Study_Model": "Human",
        "Evidence_Level": "Clinical / human evidence",
    }
    result = _validate(row)
    assert result["study_type_consistency"]["passed"] is True


# --- Missing-field handling ---------------------------------------------------

def test_missing_plant_identity_is_not_assessable():
    row = {"Notes": "reduced sleep latency in a randomized trial"}
    result = _validate(row, plant_name="")
    assert result["plant_identity_resolved"]["passed"] is False
    assert result["overall_status"] == NOT_ASSESSABLE


def test_missing_critical_fields_are_reported_not_guessed():
    row = {"Scientific_Name": "Valeriana officinalis"}
    normalized = normalize_evidence_record(row)
    result = validate_evidence_record(
        row, plant_name="Valeriana officinalis", indication="sleep",
        normalized_fields=normalized,
    )
    assert "indication" in result["missing_critical_fields"]["missing_fields"] or \
           "study_type" in result["missing_critical_fields"]["missing_fields"]
    assert result["missing_critical_fields"]["passed"] is False


# --- Contradictory evidence ----------------------------------------------------

def test_contradictory_evidence_is_flagged():
    row = {
        "Scientific_Name": "Valeriana officinalis", "Target_Indication": "sleep",
        "Notes": "Valeriana officinalis showed no significant difference from placebo in this "
                 "randomized trial for sleep; the trial failed to demonstrate efficacy.",
    }
    result = _validate(row)
    assert result["contradictory_or_negative_evidence"]["has_negative_evidence"] is True
    assert result["overall_status"] in (VALID_WITH_LIMITATIONS, REJECTED)


def test_clean_positive_evidence_is_not_flagged_as_contradictory():
    row = {
        "Notes": "Valeriana officinalis significantly improved sleep quality in a randomized, "
                 "placebo-controlled human trial for insomnia.",
        "Study_Model": "Human", "Evidence_Level": "Clinical / human evidence",
        "PMID": "555", "Primary_Outcome": "Sleep quality improved.",
    }
    result = _validate(row)
    assert result["contradictory_or_negative_evidence"]["has_negative_evidence"] is False


# --- Overall status vocabulary ------------------------------------------------

def test_overall_status_is_always_one_of_the_four_allowed_values():
    rows = [
        {},
        {"Scientific_Name": "Valeriana officinalis"},
        {"Notes": "Valeriana officinalis reduced sleep latency in a randomized human trial.",
         "Scientific_Name": "Valeriana officinalis", "Study_Model": "Human",
         "Evidence_Level": "Clinical / human evidence", "PMID": "1", "Primary_Outcome": "improved"},
    ]
    for row in rows:
        result = _validate(row)
        assert result["overall_status"] in (VALID, VALID_WITH_LIMITATIONS, REJECTED, NOT_ASSESSABLE)


def test_clean_direct_human_evidence_is_fully_valid():
    row = {
        "Scientific_Name": "Valeriana officinalis", "Target_Indication": "sleep",
        "Notes": "Valeriana officinalis significantly reduced sleep latency in a randomized, "
                 "placebo-controlled human trial for sleep over 8 weeks with n=84 participants.",
        "Study_Model": "Human", "Evidence_Level": "Clinical / human evidence",
        "PMID": "123456", "Primary_Outcome": "Sleep latency reduced.",
        "Dosage_Form": "Infusion",
    }
    result = _validate(row, seen=set())
    assert result["overall_status"] == VALID


# --- Compound similarity is never used as proof ------------------------------

def test_compound_similarity_field_is_never_read_by_any_check():
    row_without_compound_link = {
        "Scientific_Name": "Valeriana officinalis",
        "Notes": "Valeriana officinalis reduced sleep latency in a randomized human trial.",
        "Study_Model": "Human", "Evidence_Level": "Clinical / human evidence",
        "PMID": "1", "Primary_Outcome": "improved",
        "Shared_or_Similar_Compound": "",
    }
    row_with_strong_compound_link = dict(row_without_compound_link)
    row_with_strong_compound_link["Shared_or_Similar_Compound"] = "Valerenic acid; Valepotriates; Hesperidin"
    result_without = _validate(row_without_compound_link, seen=set())
    result_with = _validate(row_with_strong_compound_link, seen=set())
    # Every check result must be identical regardless of compound data —
    # proves no check reads compound similarity as evidence of efficacy.
    for key in result_without:
        if key == "overall_status":
            continue
        assert result_without[key] == result_with[key], f"{key} differed based on compound similarity data"


# --- Row-order independence --------------------------------------------------

def test_validation_result_is_independent_of_processing_order():
    row_a = {"Scientific_Name": "Valeriana officinalis",
             "Notes": "Valeriana officinalis reduced sleep latency.", "PMID": "1"}
    row_b = {"Scientific_Name": "Melissa officinalis",
             "Notes": "Melissa officinalis improved sleep quality.", "PMID": "2"}

    seen_forward = set()
    forward = [_validate(row_a, plant_name="Valeriana officinalis", seen=seen_forward),
               _validate(row_b, plant_name="Melissa officinalis", seen=seen_forward)]

    seen_backward = set()
    backward = [_validate(row_b, plant_name="Melissa officinalis", seen=seen_backward),
                _validate(row_a, plant_name="Valeriana officinalis", seen=seen_backward)]

    assert forward[0]["plant_specific_attribution"] == backward[1]["plant_specific_attribution"]
    assert forward[1]["plant_specific_attribution"] == backward[0]["plant_specific_attribution"]
    # Neither ever becomes a duplicate of the other just because of order.
    assert forward[0]["duplicate_study"]["is_duplicate"] is False
    assert forward[1]["duplicate_study"]["is_duplicate"] is False
    assert backward[0]["duplicate_study"]["is_duplicate"] is False
    assert backward[1]["duplicate_study"]["is_duplicate"] is False


# --- Backward compatibility ---------------------------------------------------

def test_empty_row_never_crashes_and_is_not_assessable():
    result = _validate({}, plant_name="", indication="")
    assert result["overall_status"] == NOT_ASSESSABLE


def test_validate_without_precomputed_normalized_fields_still_works():
    # normalized_fields is optional — computed internally if omitted, so
    # this stays usable by a caller that hasn't been updated to call
    # normalize_evidence_record() itself first.
    row = {"Scientific_Name": "Valeriana officinalis",
           "Notes": "Valeriana officinalis reduced sleep latency."}
    result = validate_evidence_record(row, plant_name="Valeriana officinalis", indication="sleep")
    assert "overall_status" in result
