
from canonical_scientific_assertion import (
    resolve_record_direction, CANONICAL_POSITIVE, CANONICAL_NULL,
    CANONICAL_MIXED, CANONICAL_UNCLEAR,
)

def fallback(_):
    return "negative"

def test_source_structured_direction_overrides_text_fallback():
    rec={"source_result_direction":"Positive","assertion_text":"wording the fallback would misread"}
    r=resolve_record_direction(rec,fallback_fn=fallback)
    assert r.direction == CANONICAL_POSITIVE
    assert r.provenance == "source_result_direction"

def test_llm_structured_direction_is_used_when_source_direction_missing():
    rec={"llm_result_direction":"Neutral","assertion_text":"effective"}
    r=resolve_record_direction(rec,fallback_fn=lambda _: "positive")
    assert r.direction == CANONICAL_NULL
    assert r.provenance == "llm_result_direction"

def test_explicit_structured_unknown_does_not_get_reinterpreted_as_positive():
    rec={"source_result_direction":"Unknown","assertion_text":"contains efficacy wording"}
    r=resolve_record_direction(rec,fallback_fn=lambda _: "positive")
    assert r.direction == CANONICAL_UNCLEAR

def test_missing_structured_direction_abstains_instead_of_using_text_fallback():
    rec={"assertion_text":"legacy record"}
    r=resolve_record_direction(rec,fallback_fn=lambda _: "mixed")
    assert r.direction == CANONICAL_UNCLEAR
    assert r.provenance == "missing_structured_direction"


def test_body_assessment_uses_structured_direction_not_conflicting_text_fallback():
    from evidence_body_assessment import assess_evidence_body, BodyDirection
    records=[
        {
            "source_type":"SYSTEMATIC_REVIEW",
            "source_result_direction":"Positive",
            "assertion_text":"Legacy fallback wording is intentionally unrecognized.",
            "source_year":2025,
            "evidence_record_id":"a",
        },
        {
            "source_type":"SYSTEMATIC_REVIEW",
            "source_result_direction":"Positive",
            "assertion_text":"Another wording the fallback does not know.",
            "source_year":2024,
            "evidence_record_id":"b",
        },
    ]
    body=assess_evidence_body(
        records,
        direction_fn=lambda _: "unclear",
        limitation_fn=lambda _: "none",
    )
    assert body.direction == BodyDirection.SUPPORTIVE


def test_structured_mixed_governing_direction_is_material_conflict():
    from final_decision_policy import resolve_scientific_evidence, ScientificEvidenceSignal
    records=[{
        "source_type":"SYSTEMATIC_REVIEW",
        "source_result_direction":"Mixed",
        "assertion_text":"Source-reported structured direction is mixed.",
        "source_year":2025,
        "evidence_record_id":"mixed-a",
    }]
    r=resolve_scientific_evidence(records)
    assert r.signal == ScientificEvidenceSignal.CONFLICT

def test_legacy_unstructured_mixed_text_abstains_until_backfilled():
    from final_decision_policy import resolve_scientific_evidence, ScientificEvidenceSignal
    records=[{
        "source_type":"SYSTEMATIC_REVIEW",
        "assertion_text":"Meta-analysis found benefit but results were mixed across outcomes.",
        "source_year":2025,
        "evidence_record_id":"legacy-mixed",
    }]
    r=resolve_scientific_evidence(records, allow_legacy_text_fallback=False)
    assert r.signal == ScientificEvidenceSignal.UNRESOLVED
