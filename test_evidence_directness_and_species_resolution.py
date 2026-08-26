"""Regression tests for three generalizable root-cause fixes (2026-08-26),
triggered by a sleep-indication export where Citrus limon (weak/indirect
evidence) outranked Lavandula angustifolia (direct human evidence):

1. Species/entity-resolution: a short common name (e.g. "lemon", Citrus
   limon) must never absorb evidence that actually names a different,
   longer common name it happens to be a whole-word prefix of (e.g.
   "lemon verbena", Aloysia citrodora). See
   research_engine.py::_build_alias_extension_map /
   _extract_catalogued_plants.

2. Evidence-hierarchy wiring: study-type classification for scoring must
   come from the phrase-aware 8-tier classifier
   (evidence_hierarchy_classifier.py), not a bare "human"/"clinical"
   substring check that also matches non-clinical text such as "human
   keratinocytes" (an in-vitro cell-line study). See
   indication_candidate_discovery.py::_record_evidence_characteristics.

3. Direct vs. indirect evidence: a query term appearing only in a
   record's mechanism/target annotation (e.g. "GABAergic modulation...
   relevant to sleep") must not score as strongly as a query term
   appearing in the record's own reported outcome (e.g. "reduced sleep
   latency"). See general_indication_relevance.py's outcome_text
   parameter and indication_candidate_discovery.py's tier2/outcome_text
   split.

No indication- or plant-specific vocabulary is added anywhere in these
fixes or these tests -- every case below uses invented plant/indication
names, or names chosen only to mirror the reported real-world pair, to
prove the fixes are structural, not case-specific patches.
"""
from collections import defaultdict

import pandas as pd

from research_engine import _extract_catalogued_plants, _build_alias_extension_map
from general_indication_relevance import (
    build_indication_profile,
    score_record_relevance_hybrid,
    MATCH_EXPLICIT_FIELD_OVERLAP,
    MATCH_OUTCOME_OR_MECHANISM_SUPPORT,
)
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


# ---------------------------------------------------------------------------
# 1. Species/entity resolution
# ---------------------------------------------------------------------------

def _lemon_alias_catalog():
    return {
        "Citrus limon": {("citrus limon", "scientific"), ("lemon", "common")},
        "Aloysia citrodora": {("aloysia citrodora", "scientific"), ("lemon verbena", "common")},
    }


def test_short_common_name_does_not_absorb_a_longer_unrelated_plants_name():
    """A record about "lemon verbena" and sleep must be attributed only to
    Aloysia citrodora -- never to Citrus limon, even though "lemon" is a
    literal whole-word prefix of "lemon verbena"."""
    records = [{
        "Title": "Effect of lemon verbena extract on sleep quality in adults",
        "Abstract": "A randomized controlled trial of lemon verbena tea on sleep.",
        "Source_Type": "PubMed", "PMID": "111",
    }]
    ranked, diagnostics = _extract_catalogued_plants(
        records, _lemon_alias_catalog(), indication_terms=["sleep"],
    )
    assert "Aloysia citrodora" in ranked
    assert "Citrus limon" not in ranked
    assert diagnostics["Aloysia citrodora"]["matched_aliases"] == ["lemon verbena"]


def test_bare_short_common_name_still_matches_its_own_plant():
    """The fix must not suppress genuine matches -- a record that mentions
    only "lemon" (not "lemon verbena") still credits Citrus limon."""
    records = [{
        "Title": "Lemon peel flavonoids and sleep-related receptor binding",
        "Abstract": "Effects of lemon extract on sleep in a rodent model.",
        "Source_Type": "PubMed", "PMID": "222",
    }]
    ranked, diagnostics = _extract_catalogued_plants(
        records, _lemon_alias_catalog(), indication_terms=["sleep"],
    )
    assert "Citrus limon" in ranked
    assert "Aloysia citrodora" not in ranked


def test_alias_extension_map_only_covers_common_names_across_different_plants():
    """Scientific names are unambiguous and must never be guarded (they
    are handled by botanical_taxonomy.py instead), and an alias never
    extends against another alias of its OWN plant."""
    catalog = {
        "Citrus limon": {("citrus limon", "scientific"), ("lemon", "common")},
        "Aloysia citrodora": {("aloysia citrodora", "scientific"), ("lemon verbena", "common")},
        "Melissa officinalis": {("melissa officinalis", "scientific"), ("lemon balm", "common")},
    }
    extensions = _build_alias_extension_map(catalog)
    assert extensions[("Citrus limon", "lemon")] == {"lemon verbena", "lemon balm"}
    assert ("Citrus limon", "citrus limon") not in extensions


# ---------------------------------------------------------------------------
# 2. Evidence-hierarchy wiring (human/preclinical false positives)
# ---------------------------------------------------------------------------

def _engine(candidate_data, evidence_rows):
    evidence = pd.DataFrame(evidence_rows)
    return BotanicalRDCandidateEngine(
        evidence_df=evidence, candidate_data=candidate_data, use_live_search=False,
        plant_compounds_df=pd.DataFrame(), compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_records_df=pd.DataFrame(),
    )


def test_human_cell_line_text_is_not_misclassified_as_clinical_evidence():
    """"human keratinocytes" is an in-vitro cell-line study, not a human
    clinical trial. The old bare-substring "human" check misclassified
    this as "Direct human evidence"; the wired-in hierarchy classifier
    must correctly place it as preclinical instead."""
    candidate_data = [
        {"Scientific_Name": "Fictus dermalis", "Known_Active_Compounds": ["Fictusol"],
         "Known_Targets": [], "Indications": []},
    ]
    evidence_rows = [{
        "plant": "Fictus dermalis", "Source_URL": "https://example.org/derm1",
        "title": "Fictus dermalis extract improves skin firmness",
        "abstract": (
            "In vitro assay in cultured human keratinocytes demonstrated "
            "increased collagen synthesis relevant to skin firmness."
        ),
    }]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("skin firmness", discovery_mode="indication")
    row = out[out["Alternative_Plant"] == "Fictus dermalis"].iloc[0]
    assert row["Candidate_Evidence_Strength_Tier"] == "Direct preclinical evidence"
    assert row["Candidate_Evidence_Strength_Tier"] != "Direct human evidence"


def test_genuine_human_rct_still_classified_as_human_evidence():
    """The fix must not create a false negative in the other direction --
    a real human RCT is still recognized as human evidence."""
    candidate_data = [
        {"Scientific_Name": "Fictus somnians", "Known_Active_Compounds": ["Fictusol"],
         "Known_Targets": [], "Indications": []},
    ]
    evidence_rows = [{
        "plant": "Fictus somnians", "Source_URL": "https://example.org/somn1",
        "title": "Fictus somnians for insomnia",
        "abstract": (
            "A randomized controlled trial found Fictus somnians extract "
            "reduced sleep latency and improved sleep quality in adults "
            "with insomnia."
        ),
    }]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("sleep", discovery_mode="indication")
    row = out[out["Alternative_Plant"] == "Fictus somnians"].iloc[0]
    assert row["Candidate_Evidence_Strength_Tier"] == "Direct human evidence"


# ---------------------------------------------------------------------------
# 3. Direct vs. indirect evidence
# ---------------------------------------------------------------------------

def test_mechanism_only_literal_match_is_not_scored_as_direct_evidence():
    """A query term appearing only in a mechanism/target annotation must
    score as outcome_or_mechanism_support (indirect), never as
    explicit_field_overlap (direct) -- generalizes to any indication."""
    corpus = [
        "GABAergic modulation potentially relevant to sleep and sedation",
        "Menthol activity in cultured neurons; modulated calcium channel activity in vitro.",
    ]
    profile = build_indication_profile("sleep", corpus)
    result = score_record_relevance_hybrid(
        profile,
        tier1_text="",
        tier2_text="GABAergic modulation potentially relevant to sleep and sedation",
        tier3_text="Menthol activity in cultured neurons; modulated calcium channel activity in vitro.",
        outcome_text="",
    )
    assert result.match_type == MATCH_OUTCOME_OR_MECHANISM_SUPPORT
    assert result.match_type != MATCH_EXPLICIT_FIELD_OVERLAP


def test_reported_outcome_literal_match_is_scored_as_direct_evidence():
    """The same query term, when it appears in the record's OWN reported
    outcome rather than only its mechanism annotation, is direct evidence."""
    corpus = ["Reduced sleep latency and improved sleep quality in a randomized trial"]
    profile = build_indication_profile("sleep", corpus)
    result = score_record_relevance_hybrid(
        profile,
        tier1_text="",
        tier2_text="GABAergic system",
        tier3_text="",
        outcome_text="Reduced sleep latency and improved sleep quality in a randomized trial",
    )
    assert result.match_type == MATCH_EXPLICIT_FIELD_OVERLAP


def test_end_to_end_direct_outcome_outranks_mechanism_only_mention():
    """Full production path: a plant with a genuine reported-outcome RCT
    must outrank a plant whose only connection is a mechanism annotation
    that happens to literally mention the query term."""
    candidate_data = [
        {"Scientific_Name": "Fictus mechanisticus", "Known_Active_Compounds": ["Fictusol"],
         "Known_Targets": [], "Indications": []},
        {"Scientific_Name": "Fictus directus", "Known_Active_Compounds": ["Fictusin"],
         "Known_Targets": [], "Indications": []},
    ]
    evidence_rows = [
        {
            "plant": "Fictus mechanisticus", "Source_URL": "https://example.org/mech1",
            "title": "Fictusol activity in cultured neurons",
            "abstract": "Fictusol modulated calcium channel activity in vitro.",
            "mechanism": "GABAergic modulation potentially relevant to sleep and sedation",
        },
        {
            "plant": "Fictus directus", "Source_URL": "https://example.org/dir1",
            "title": "Fictus directus for insomnia",
            "abstract": (
                "A randomized controlled trial found Fictus directus reduced "
                "sleep latency and improved sleep quality in adults with insomnia."
            ),
        },
    ]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("sleep", discovery_mode="indication")
    mech_row = out[out["Alternative_Plant"] == "Fictus mechanisticus"].iloc[0]
    direct_row = out[out["Alternative_Plant"] == "Fictus directus"].iloc[0]
    assert direct_row["R&D_Opportunity_Score"] > mech_row["R&D_Opportunity_Score"]
    assert mech_row["Indication_Match_Type"] == MATCH_OUTCOME_OR_MECHANISM_SUPPORT
    assert direct_row["Indication_Match_Type"] == MATCH_EXPLICIT_FIELD_OVERLAP


# ---------------------------------------------------------------------------
# 4. Negative/null reported result must reduce the discovery-stage score
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 5. Preparation/route-of-administration transferability ("tea" recognition)
# ---------------------------------------------------------------------------

def test_bare_tea_is_recognized_as_an_aqueous_infusion_preparation():
    """Querying with dosage_form="tea" (the natural phrasing, far more
    common than "herbal tea") must actually populate a preparation target
    -- previously it silently produced no target at all, disabling the
    whole preparation-applicability gate for the single most common way
    anyone actually asks for this product."""
    from standard_evidence_builder import (
        preparation_category_from_text, preparation_from_product_form,
        canonical_preparation_identity,
    )
    assert preparation_category_from_text("tea") == "aqueous"
    assert preparation_category_from_text("sleep tea") == "aqueous"
    assert preparation_from_product_form("tea") == "tea"
    assert canonical_preparation_identity("tea") == "infusion"
    # "tea tree" is a different, essential-oil preparation and must not be
    # swept into the aqueous-infusion category just because it contains
    # the word "tea".
    assert preparation_category_from_text("tea tree oil") == ""
    assert canonical_preparation_identity("tea tree oil") == ""


def test_essential_oil_evidence_is_flagged_mismatch_for_a_tea_query():
    """Full production path: a plant whose only evidence is essential-oil
    inhalation/aromatherapy must be flagged Mismatch (and scored lower)
    for a tea-dosage-form query, never silently treated as Compatible --
    mirrors a real reported issue where Lavandula angustifolia (essential
    oil evidence only) outranked Melissa officinalis (genuine oral
    infusion/tea evidence) for a sleep-tea query."""
    candidate_data = [
        {"Scientific_Name": "Fictus oleosus", "Known_Active_Compounds": ["Fictol"],
         "Known_Targets": [], "Indications": []},
        {"Scientific_Name": "Fictus infusus", "Known_Active_Compounds": ["Fictusin"],
         "Known_Targets": [], "Indications": []},
    ]
    evidence_rows = [
        {
            "plant": "Fictus oleosus", "Source_URL": "https://example.org/oil1",
            "title": "Fictus oleosus for sleep quality",
            "abstract": "A meta-analysis found Fictus oleosus essential oil inhalation aromatherapy improved sleep quality.",
            "preparation": "essential oil inhalation aromatherapy",
        },
        {
            "plant": "Fictus infusus", "Source_URL": "https://example.org/inf1",
            "title": "Fictus infusus for insomnia",
            "abstract": "A randomized controlled trial found Fictus infusus oral aqueous infusion tea improved sleep quality and insomnia severity.",
            "preparation": "oral aqueous infusion tea",
        },
    ]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("sleep", dosage_form="tea", discovery_mode="indication")
    oil_row = out[out["Alternative_Plant"] == "Fictus oleosus"].iloc[0]
    infusion_row = out[out["Alternative_Plant"] == "Fictus infusus"].iloc[0]
    assert oil_row["Preparation_Applicability"] == "Mismatch"
    assert infusion_row["Preparation_Applicability"] == "Compatible"
    assert infusion_row["R&D_Opportunity_Score"] > oil_row["R&D_Opportunity_Score"]


def test_negative_rct_result_is_penalized_not_rewarded():
    """A plant whose only RCT explicitly found NO benefit must score well
    below a plant whose RCT found a real benefit -- the previous discovery-
    stage formula computed evidence_points purely from study-design TIER
    (both are "Clinical trial") and ignored the reported direction, so a
    negative RCT scored the same as a positive one of the same design.
    This regression case mirrors a real reported issue: Bacopa monnieri
    ranked near Valeriana officinalis despite two negative human RCTs for
    sleep."""
    candidate_data = [
        {"Scientific_Name": "Fictus negativus", "Known_Active_Compounds": ["Fictusol"],
         "Known_Targets": [], "Indications": []},
        {"Scientific_Name": "Fictus positivus", "Known_Active_Compounds": ["Fictusin"],
         "Known_Targets": [], "Indications": []},
    ]
    evidence_rows = [
        {
            "plant": "Fictus negativus", "Source_URL": "https://example.org/neg1",
            "title": "Fictus negativus for poor sleep",
            "abstract": (
                "A randomized controlled trial of Fictus negativus for sleep quality."
            ),
            "primary_outcome": "No significant difference vs placebo in sleep quality",
        },
        {
            "plant": "Fictus positivus", "Source_URL": "https://example.org/pos1",
            "title": "Fictus positivus for insomnia",
            "abstract": (
                "A randomized controlled trial found Fictus positivus reduced "
                "sleep latency and improved sleep quality in adults with insomnia."
            ),
        },
    ]
    engine = _engine(candidate_data, evidence_rows)
    out = engine.run("sleep", discovery_mode="indication")
    neg_row = out[out["Alternative_Plant"] == "Fictus negativus"].iloc[0]
    pos_row = out[out["Alternative_Plant"] == "Fictus positivus"].iloc[0]
    assert neg_row["R&D_Opportunity_Score"] < pos_row["R&D_Opportunity_Score"] - 15
    assert neg_row["Go_Investigate_Hold_NoGo"].startswith("Hold")
    assert neg_row["Decision_Class_AH"] == "F"
