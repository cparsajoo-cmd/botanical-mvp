import pandas as pd

from general_indication_relevance import build_indication_profile, corpus_texts_from_records
from indication_candidate_discovery import _catalogue_prescreen_before_expensive_loop


class _Engine:
    @staticmethod
    def _pick(row, names):
        for name in names:
            value = row.get(name, "")
            if value not in (None, ""):
                return value
        return ""


def test_large_catalogue_is_reduced_before_expensive_loop_and_legacy_query_stamp_is_not_mandatory():
    candidates = pd.DataFrame([
        {"Scientific_Name": f"Plant {i}", "candidate_origin": "internal_catalogue", "already_in_supabase": True}
        for i in range(2000)
    ])
    evidence_index = {}
    for i in range(10):
        evidence_index[f"plant {i}"] = [{
            "tier1_text": "Sleep and relaxation",
            "requested_target_indication": "Sleep and relaxation",
            "tier2_text": "",
            "tier3_text": "randomized trial sleep quality insomnia",
            "outcome_text": "sleep quality improved",
        }]
    # Simulates historical rows in which the requested query was stamped into
    # Target_Indication even though the source text is about another condition.
    for i in range(10, 1010):
        evidence_index[f"plant {i}"] = [{
            "tier1_text": "Sleep and relaxation",
            "requested_target_indication": "Sleep and relaxation",
            "tier2_text": "antioxidant",
            "tier3_text": "diabetes glycemic glucose study",
            "outcome_text": "glucose reduced",
        }]
    profile = build_indication_profile("Sleep and relaxation", corpus_texts_from_records(evidence_index))
    kept, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(), candidates, evidence_index, profile, "Sleep and relaxation", exploratory_budget=90
    )
    assert len(kept) == 90
    assert set(range(10)).issubset(set(kept.index))
    assert (audit["PreScreen_Reason"] == "DIRECT_INDICATION_EVIDENCE").sum() == 10
    assert (audit["PreScreen_Status"] == "PRESCREENED_OUT").sum() == 1910


def test_stage2_novel_candidate_is_mandatory_even_without_internal_evidence():
    candidates = pd.DataFrame([
        {"Scientific_Name": "Known plant", "candidate_origin": "internal_catalogue", "already_in_supabase": True},
        {"Scientific_Name": "Novel plant", "candidate_origin": "literature_discovered", "already_in_supabase": False},
    ])
    evidence_index = {}
    profile = build_indication_profile("Novel indication", [])
    kept, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(), candidates, evidence_index, profile, "Novel indication", exploratory_budget=0
    )
    assert "Novel plant" in set(kept["Scientific_Name"])
    novel = audit[audit["Alternative_Plant"] == "Novel plant"].iloc[0]
    assert novel["PreScreen_Status"] == "SENT_TO_FULL_SCORING"
    assert novel["PreScreen_Reason"] == "STAGE2_NOVEL"
