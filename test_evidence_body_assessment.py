
from evidence_body_assessment import (
    assess_evidence_body, BodyDirection, BodyCertainty,
)

def _dir(text):
    t=text.lower()
    if "little to no difference" in t or "no benefit" in t:
        return "null"
    if "mixed" in t:
        return "mixed"
    if "improved" in t or "benefit" in t or "effective" in t:
        return "positive"
    return "unclear"

def _lim(text):
    t=text.lower()
    if "insufficient for firm conclusions" in t:
        return "firm_uncertainty"
    if "heterogeneity" in t or "further trials" in t or "risk of bias" in t:
        return "caution"
    return "none"

def test_two_clean_systematic_reviews_can_reach_high_certainty_support():
    records=[
        {"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Meta-analysis found benefit.","source_year":2023,"evidence_record_id":"a"},
        {"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Systematic review found improved outcomes.","source_year":2024,"evidence_record_id":"b"},
    ]
    b=assess_evidence_body(records,direction_fn=_dir,limitation_fn=_lim)
    assert b.direction == BodyDirection.SUPPORTIVE
    assert b.certainty == BodyCertainty.HIGH

def test_single_systematic_review_is_not_unconditional_high_certainty():
    records=[{"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Meta-analysis found benefit.","source_year":2024}]
    b=assess_evidence_body(records,direction_fn=_dir,limitation_fn=_lim)
    assert b.certainty == BodyCertainty.MODERATE

def test_material_limitation_downgrades_body_certainty():
    records=[
        {"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Meta-analysis found benefit but substantial heterogeneity.","source_year":2024,"evidence_record_id":"a"},
        {"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Systematic review found improved outcomes.","source_year":2023,"evidence_record_id":"b"},
    ]
    b=assess_evidence_body(records,direction_fn=_dir,limitation_fn=_lim)
    assert b.certainty == BodyCertainty.MODERATE

def test_single_rct_is_not_treated_like_high_certainty_body():
    records=[{"source_type":"CLINICAL_TRIAL","study_design":"Randomized Controlled Trial","assertion_text":"Trial found improved outcomes.","source_year":2024}]
    b=assess_evidence_body(records,direction_fn=_dir,limitation_fn=_lim)
    assert b.direction == BodyDirection.SUPPORTIVE
    assert b.certainty == BodyCertainty.LOW

def test_null_governing_synthesis_is_null_body():
    records=[{"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Review found little to no difference in symptoms.","source_year":2024}]
    b=assess_evidence_body(records,direction_fn=_dir,limitation_fn=_lim)
    assert b.direction == BodyDirection.NULL_OR_NEGATIVE

def test_newer_direct_contradiction_challenges_older_supportive_synthesis():
    records=[
        {"source_type":"SYSTEMATIC_REVIEW","assertion_text":"Review found benefit.","source_year":2018,"evidence_record_id":"a"},
        {"source_type":"CLINICAL_TRIAL","study_design":"Randomized Controlled Trial","assertion_text":"Trial found no benefit.","source_year":2023,"evidence_record_id":"b"},
    ]
    b=assess_evidence_body(records,direction_fn=_dir,limitation_fn=_lim)
    assert b.direction == BodyDirection.MIXED
    assert b.has_newer_contradiction is True


def test_study_design_can_be_recovered_from_text_when_structured_field_missing():
    records=[{"assertion_text":"A randomized controlled trial reported improved outcomes versus placebo."}]
    b=assess_evidence_body(records,direction_fn=_dir,limitation_fn=_lim)
    assert b.direction == BodyDirection.SUPPORTIVE
    assert b.certainty == BodyCertainty.LOW
