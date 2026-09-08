"""Regression tests for the Stage-5 Mechanistic Hypothesis Entry Path
(external review, 2026-09-08): a catalogue plant with ZERO evidence
records for the requested indication, but an explicit Known_Targets/
mechanism match on its own profile, must survive
_catalogue_prescreen_before_expensive_loop() instead of being silently
discarded before discover_indication_candidates()'s main loop ever gets a
chance to recognise it as a profile-derived hypothesis.
"""
import pandas as pd

from general_indication_relevance import build_indication_profile, corpus_texts_from_records
from indication_candidate_discovery import _catalogue_prescreen_before_expensive_loop


class _Engine:
    def __init__(self, plant_compounds_df=None):
        # getattr(engine, "plant_compounds_df", None) is how the prescreen
        # reads this -- omitting the attribute entirely (as the older
        # fixture in test_stage5_pre_engine_prescreen.py does) must degrade
        # safely too; both are exercised across this file's tests.
        if plant_compounds_df is not None:
            self.plant_compounds_df = plant_compounds_df

    @staticmethod
    def _pick(row, names):
        for name in names:
            try:
                value = row.get(name, "")
            except AttributeError:
                value = ""
            if (
                value is not None
                and str(value).strip()
                and str(value).strip().lower() not in ("nan", "none", "null")
            ):
                return str(value).strip()
        return ""


def _profile(indication, evidence_index=None):
    evidence_index = evidence_index or {}
    return build_indication_profile(indication, corpus_texts_from_records(evidence_index))


def test_zero_evidence_plant_with_matching_target_profile_survives_prescreen():
    # The exact scenario from the architecture review: a hypothetical
    # plant with no evidence records at all, but Known_Targets containing
    # a GABA-A receptor mention -- must now reach full scoring.
    candidates = pd.DataFrame([
        {
            "Scientific_Name": "Obscura testii",
            "Known_Targets": ["GABA-A receptor"],
            "Known_Active_Compounds": ["Novelol"],
            "Indications_Text": "",
            "candidate_origin": "internal_catalogue",
            "already_in_supabase": True,
        },
        {
            "Scientific_Name": "Irrelevanta planta",
            "Known_Targets": ["Unrelated cosmetic astringent target"],
            "Known_Active_Compounds": ["Tannin X"],
            "Indications_Text": "",
            "candidate_origin": "internal_catalogue",
            "already_in_supabase": True,
        },
    ])
    indication = "Sleep and relaxation"
    profile = _profile(indication)

    retained, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(), candidates, {}, profile, indication,
    )

    retained_names = set(retained["Scientific_Name"])
    assert "Obscura testii" in retained_names
    assert "Irrelevanta planta" not in retained_names

    reason = audit.loc[
        audit["Alternative_Plant"] == "Obscura testii", "PreScreen_Reason"
    ].iloc[0]
    assert reason == "PROFILE_MECHANISTIC_HYPOTHESIS"

    other_reason = audit.loc[
        audit["Alternative_Plant"] == "Irrelevanta planta", "PreScreen_Reason"
    ].iloc[0]
    assert other_reason == "NO_OR_LOW_INDICATION_SIGNAL"


def test_compound_alone_is_never_the_entry_gate():
    # A plant whose ONLY signal is a compound (no target/mechanism text
    # relevant to the indication) must NOT enter -- entry is gated on
    # target/mechanism relevance, never compound identity by itself.
    candidates = pd.DataFrame([{
        "Scientific_Name": "Quercetin-only plant",
        "Known_Targets": "",
        "Known_Active_Compounds": ["Quercetin"],
        "Indications_Text": "",
        "candidate_origin": "internal_catalogue",
        "already_in_supabase": True,
    }])
    indication = "Sleep and relaxation"
    profile = _profile(indication)

    retained, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(), candidates, {}, profile, indication,
    )
    assert retained.empty
    assert audit.iloc[0]["PreScreen_Reason"] == "NO_OR_LOW_INDICATION_SIGNAL"


def test_missing_plant_compounds_df_degrades_safely_no_specificity_signal():
    # An engine with no plant_compounds_df at all (older fixture, or a
    # Supabase-unavailable run) must not crash -- the mechanistic entry
    # check still runs on Known_Targets text alone, just without a
    # specificity tie-break.
    candidates = pd.DataFrame([{
        "Scientific_Name": "Obscura testii",
        "Known_Targets": ["GABA-A receptor"],
        "Known_Active_Compounds": ["Novelol"],
        "Indications_Text": "",
        "candidate_origin": "internal_catalogue",
        "already_in_supabase": True,
    }])
    indication = "Sleep and relaxation"
    profile = _profile(indication)

    retained, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(plant_compounds_df=None), candidates, {}, profile, indication,
    )
    assert "Obscura testii" in set(retained["Scientific_Name"])


def test_evidence_based_admission_is_never_relabeled_mechanistic():
    # A plant with real, direct evidence must keep its original reason --
    # the new mechanistic path must never reclassify an existing admission
    # path.
    candidates = pd.DataFrame([{
        "Scientific_Name": "Valeriana officinalis",
        "Known_Targets": ["GABA-A receptor"],
        "Known_Active_Compounds": ["Valerenic acid"],
        "Indications_Text": "",
        "candidate_origin": "internal_catalogue",
        "already_in_supabase": True,
    }])
    evidence_index = {
        "valeriana officinalis": [{
            "tier1_text": "Sleep and relaxation",
            "requested_target_indication": "",
            "tier2_text": "",
            "tier3_text": "randomized trial sleep quality insomnia",
            "outcome_text": "sleep quality improved",
        }],
    }
    indication = "Sleep and relaxation"
    profile = _profile(indication, evidence_index)

    retained, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(), candidates, evidence_index, profile, indication,
    )
    assert "Valeriana officinalis" in set(retained["Scientific_Name"])
    reason = audit.iloc[0]["PreScreen_Reason"]
    assert reason == "DIRECT_INDICATION_EVIDENCE"


def test_mechanistic_budget_is_independent_of_exploratory_budget():
    # A tiny exploratory_budget (evidence-based) must not restrict the
    # separate mechanistic pool, and vice versa.
    candidates = pd.DataFrame([
        {
            "Scientific_Name": f"Mechanistic plant {i}",
            "Known_Targets": ["GABA-A receptor"],
            "Known_Active_Compounds": [f"Compound {i}"],
            "Indications_Text": "",
            "candidate_origin": "internal_catalogue",
            "already_in_supabase": True,
        }
        for i in range(5)
    ])
    indication = "Sleep and relaxation"
    profile = _profile(indication)

    retained, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(), candidates, {}, profile, indication,
        exploratory_budget=0, mechanistic_budget=5,
    )
    assert len(retained) == 5


def test_mechanistic_budget_caps_the_pool_and_prioritizes_rarer_compounds():
    # More profile-relevant candidates than the mechanistic budget allows
    # -- the rarer compound (fewer plants in the real occurrence index)
    # must win the tie-break.
    candidates = pd.DataFrame([
        {
            "Scientific_Name": "Rare compound plant",
            "Known_Targets": ["GABA-A receptor"],
            "Known_Active_Compounds": ["Rarolide"],
            "Indications_Text": "",
            "candidate_origin": "internal_catalogue",
            "already_in_supabase": True,
        },
        {
            "Scientific_Name": "Common compound plant",
            "Known_Targets": ["GABA-A receptor"],
            "Known_Active_Compounds": ["Commonol"],
            "Indications_Text": "",
            "candidate_origin": "internal_catalogue",
            "already_in_supabase": True,
        },
    ])
    plant_compounds_df = pd.DataFrame(
        [{"scientific_name": "Rare compound plant", "compound_name": "Rarolide", "target": "GABA-A receptor"}]
        + [
            {"scientific_name": f"Other plant {i}", "compound_name": "Commonol", "target": ""}
            for i in range(50)
        ]
        + [{"scientific_name": "Common compound plant", "compound_name": "Commonol", "target": "GABA-A receptor"}]
    )
    indication = "Sleep and relaxation"
    profile = _profile(indication)

    retained, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(plant_compounds_df=plant_compounds_df), candidates, {}, profile, indication,
        mechanistic_budget=1,
    )
    assert list(retained["Scientific_Name"]) == ["Rare compound plant"]


def test_specificity_uses_only_compounds_linked_to_relevant_target():
    """An unrelated rare compound must not donate a discovery boost.

    Plant A has a relevant GABA link through VERY COMMON Commonol, plus a rare
    RareUnrelated compound tied only to an unrelated target. Plant B has the
    same GABA relevance through Moderatol. With mechanistic_budget=1, B should
    win on relevant-link specificity; the old independent aggregation would
    incorrectly let A borrow RareUnrelated's rarity and win.
    """
    candidates = pd.DataFrame([
        {
            "Scientific_Name": "Plant A",
            "Known_Targets": ["GABA-A receptor", "Unrelated enzyme"],
            "Known_Active_Compounds": ["Commonol", "RareUnrelated"],
            "Mechanistic_Links": [
                {"compound_name": "Commonol", "target": "GABA-A receptor", "mechanism": "GABAergic modulation"},
                {"compound_name": "RareUnrelated", "target": "Unrelated enzyme", "mechanism": "unrelated activity"},
            ],
            "Indications_Text": "",
            "candidate_origin": "internal_catalogue",
            "already_in_supabase": True,
        },
        {
            "Scientific_Name": "Plant B",
            "Known_Targets": ["GABA-A receptor"],
            "Known_Active_Compounds": ["Moderatol"],
            "Mechanistic_Links": [
                {"compound_name": "Moderatol", "target": "GABA-A receptor", "mechanism": "GABAergic modulation"},
            ],
            "Indications_Text": "",
            "candidate_origin": "internal_catalogue",
            "already_in_supabase": True,
        },
    ])
    plant_compounds_df = pd.DataFrame(
        [
            {"scientific_name": "Plant A", "compound_name": "Commonol", "target": "GABA-A receptor", "mechanism": "GABAergic modulation"},
            {"scientific_name": "Plant A", "compound_name": "RareUnrelated", "target": "Unrelated enzyme", "mechanism": "unrelated activity"},
            {"scientific_name": "Plant B", "compound_name": "Moderatol", "target": "GABA-A receptor", "mechanism": "GABAergic modulation"},
        ]
        + [
            {"scientific_name": f"Common carrier {i}", "compound_name": "Commonol", "target": ""}
            for i in range(60)
        ]
        + [
            {"scientific_name": f"Moderate carrier {i}", "compound_name": "Moderatol", "target": ""}
            for i in range(5)
        ]
    )
    indication = "Sleep and relaxation"
    profile = _profile(indication)

    retained, audit = _catalogue_prescreen_before_expensive_loop(
        _Engine(plant_compounds_df=plant_compounds_df),
        candidates, {}, profile, indication,
        exploratory_budget=0, mechanistic_budget=1,
    )

    assert set(retained["Scientific_Name"]) == {"Plant B"}
    row_a = audit.loc[audit["Alternative_Plant"] == "Plant A"].iloc[0]
    row_b = audit.loc[audit["Alternative_Plant"] == "Plant B"].iloc[0]
    assert row_a["Mechanistic_Linked_Compounds"] == "Commonol"
    assert row_b["Mechanistic_Linked_Compounds"] == "Moderatol"
    assert row_b["Mechanistic_Compound_Specificity"] > row_a["Mechanistic_Compound_Specificity"]
