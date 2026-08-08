from final_decision_policy import (
    ScientificEvidenceSignal, FinalDecisionStatus,
    resolve_scientific_evidence, decide_final,
)
from eligibility_gate import EligibilityStatus
from types import SimpleNamespace


def _eligible():
    return SimpleNamespace(status=EligibilityStatus.ELIGIBLE, gate_reason="eligible")


def test_explicit_insufficient_review_conclusion_is_null_not_unresolved():
    r = resolve_scientific_evidence([{
        "source_type": "SYSTEMATIC_REVIEW",
        "assertion_text": "The review concluded there is insufficient evidence to support the intervention for the target symptoms.",
    }])
    assert r.signal == ScientificEvidenceSignal.INSUFFICIENT


def test_explicit_appears_efficacious_review_conclusion_is_supportive():
    r = resolve_scientific_evidence([{
        "source_type": "SYSTEMATIC_REVIEW",
        "assertion_text": "The systematic review concluded the intervention appears efficacious and safe for the target disorder.",
    }])
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE
    assert decide_final(_eligible(), r).status == FinalDecisionStatus.GO


def test_supportive_review_with_explicit_across_study_variation_maps_to_caution():
    r = resolve_scientific_evidence([{
        "source_type": "SYSTEMATIC_REVIEW",
        "assertion_text": "Some clinical outcomes improved, but evidence varied across studies and endpoints.",
    }])
    assert r.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION
    assert decide_final(_eligible(), r).status == FinalDecisionStatus.GO_WITH_CAUTION


def test_same_rank_positive_and_insufficient_reviews_remain_conflict():
    r = resolve_scientific_evidence([
        {"source_type": "SYSTEMATIC_REVIEW", "assertion_text": "There is insufficient evidence to support this intervention."},
        {"source_type": "SYSTEMATIC_REVIEW", "assertion_text": "Well-designed studies showed reductions in symptoms and reported improvement in quality of life."},
    ])
    assert r.signal == ScientificEvidenceSignal.CONFLICT
    assert decide_final(_eligible(), r).status == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED


def test_direct_botanical_indication_records_survive_compound_primary_path():
    import pandas as pd
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_df=pd.DataFrame(), use_live_search=False,
    )
    plant_key = __import__('botanical_taxonomy').taxon_match_key('Example plant L.')
    evidence_index = {'marker': 'compound context text', plant_key: 'plant pooled text'}
    records_index = {
        'marker': [{'evidence_record_id':'c1','text':'compound context text','source_url':'c','authority_factor':0.6,'target_indication':'Other'}],
        plant_key: [
            {'evidence_record_id':'p1','text':'direct target review','source_url':'p','authority_factor':1.0,'target_indication':'Target condition'},
            {'evidence_record_id':'p2','text':'unrelated plant evidence','source_url':'u','authority_factor':1.0,'target_indication':'Other condition'},
        ],
    }
    text, sources, factor, records = engine._collect_raw_evidence(
        evidence_index, 'Example plant L.', 'marker', 'Target condition',
        source_index={'marker':['c']}, authority_index={}, records_index=records_index,
    )
    assert 'direct target review' in text
    assert 'unrelated plant evidence' not in text
    assert {r['evidence_record_id'] for r in records} == {'c1','p1'}
