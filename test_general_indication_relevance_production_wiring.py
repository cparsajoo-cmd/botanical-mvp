"""Mandatory production-path tests for the general indication-relevance
architecture.

These tests exercise the REAL production path end-to-end:

    discover_indication_candidates()   (indication_candidate_discovery.py)
        -> general_indication_relevance.py (authoritative engine)
    build_plant_candidate_shortlist()  (candidate_shortlisting.py)
        -> consumes the SAME per-record Indication_Match_* fields, does not
           recompute relevance independently

No test in this file adds a disease-specific dictionary entry anywhere. The
synthetic indications used ("zelunergic mucosal discomfort", "vorenthic
tissue laxity") do not exist in indication_semantics.py, any UI indication
list, or any other source file -- they are invented here, in the test, to
prove the corpus-adaptive engine works on genuinely unseen indications.
"""
import pandas as pd

from indication_candidate_discovery import discover_indication_candidates
from candidate_shortlisting import build_plant_candidate_shortlist
from indication_semantics import resolve_indication_semantics
from general_indication_relevance import (
    MATCH_EXACT_INDICATION,
    MATCH_CORPUS_DERIVED_SEMANTIC,
    MATCH_NO_MATCH,
)


class _Engine:
    """Mirrors BotanicalRDCandidateEngine._pick (the real production
    implementation) -- does not use pd.notna, so it does not choke on
    list/dict JSONB values."""

    def __init__(self, evidence_records):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame(evidence_records)
        self._candidates = pd.DataFrame()

    def set_candidates(self, candidates):
        self._candidates = pd.DataFrame(candidates)

    def _candidate_frame(self):
        return self._candidates

    def _pick(self, row, names):
        for name in names:
            try:
                value = row.get(name, "")
            except AttributeError:
                value = ""
            if (
                value is not None
                and str(value).strip()
                and str(value).lower() not in {"nan", "none", "null"}
            ):
                return str(value).strip()
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        low = text.lower()
        if "human" in low or "randomized" in low or "clinical trial" in low:
            return "Clinical / human evidence"
        return "Unknown"


# ---------------------------------------------------------------------------
# 1. Unknown indication end-to-end test
# ---------------------------------------------------------------------------

_UNSEEN_INDICATION = "zelunergic mucosal discomfort"


def test_unseen_indication_has_no_dictionary_entry_anywhere():
    """Structural proof: the synthetic phrase used below is not present in
    indication_semantics.py (or anywhere else in source code)."""
    assert resolve_indication_semantics(_UNSEEN_INDICATION) is None


def _unseen_indication_engine():
    engine = _Engine([
        {
            "Scientific_Name": "Fictus planta",
            "Evidence_Record_ID": 1,
            "Target_Indication": _UNSEEN_INDICATION,
            "Study_Type": "Randomized human clinical trial",
            "Primary_Outcome": f"Significant improvement in {_UNSEEN_INDICATION} score",
        },
        {
            "Scientific_Name": "Unrelated fictus",
            "Evidence_Record_ID": 2,
            "Target_Indication": "Type 2 diabetes",
            "Study_Type": "Randomized human clinical trial",
            "Primary_Outcome": "Reduced fasting blood glucose",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Fictus planta", "Known_Active_Compounds": "fictusol",
         "Known_Targets": "mucosal barrier", "Indications_Text": ""},
        {"Scientific_Name": "Unrelated fictus", "Known_Active_Compounds": "x",
         "Known_Targets": "ampk", "Indications_Text": ""},
    ])
    return engine


def test_unseen_indication_end_to_end_discovery_and_shortlist():
    engine = _unseen_indication_engine()
    raw = discover_indication_candidates(engine, _UNSEEN_INDICATION, dosage_form="oral")

    # The relevant plant is discovered; the unrelated plant is not.
    assert "Fictus planta" in set(raw["Alternative_Plant"])
    assert "Unrelated fictus" not in set(raw["Alternative_Plant"])

    # Authoritative match fields are present and correct at the discovery stage.
    fictus_rows = raw[raw["Alternative_Plant"] == "Fictus planta"]
    assert (fictus_rows["Indication_Match_Type"] == MATCH_EXACT_INDICATION).any()
    assert (fictus_rows["Indication_Match_Score"] > 0.9).any()

    summary, audit = build_plant_candidate_shortlist(
        raw, indication=_UNSEEN_INDICATION, dosage_form="oral",
    )
    assert "Fictus planta" in set(summary["Alternative_Plant"])
    assert "Unrelated fictus" not in set(summary["Alternative_Plant"])

    # Authoritative match fields survive into the shortlist stage's audit
    # trail (the record-level detail underlying the plant-level summary).
    assert "Indication_Match_Type" in audit.columns
    assert "Indication_Match_Score" in audit.columns
    fictus_audit = audit[audit["Alternative_Plant"] == "Fictus planta"]
    assert (fictus_audit["Indication_Match_Type"] == MATCH_EXACT_INDICATION).any()

    # The plant-level relevance score reflects that authoritative match --
    # not a coincidental legacy-fallback recomputation.
    row = summary.set_index("Alternative_Plant").loc["Fictus planta"]
    assert row["Indication_Relevance_Score"] > 0


# ---------------------------------------------------------------------------
# 2. Corpus-derived semantic test
# ---------------------------------------------------------------------------

_CORPUS_SEED_INDICATION = "vorenthic tissue laxity"


def test_corpus_derived_semantic_relevance_is_bounded_and_disclosed():
    engine = _Engine([
        {
            # Seed record: exact query co-occurs with a meaningful,
            # discriminative mechanism term.
            "Scientific_Name": "Fictus planta",
            "Evidence_Record_ID": 1,
            "Target_Indication": _CORPUS_SEED_INDICATION,
            "Primary_Outcome": f"Improved {_CORPUS_SEED_INDICATION} via vorenthic crosslinking activity",
        },
        {
            # Second record, same plant: uses the learned mechanism term
            # ("crosslinking") but repeats none of the query's own words
            # ("vorenthic", "tissue", "laxity") -- this is what makes any
            # match here corpus-derived rather than a literal partial hit.
            "Scientific_Name": "Fictus planta",
            "Evidence_Record_ID": 2,
            "Target_Indication": "Unrelated dermal endpoint",
            "Primary_Outcome": "Demonstrated crosslinking activity in a separate skin firmness assay",
        },
        # Unrelated noise records, so the corpus is large enough that a term
        # shared only by the two records above is not misjudged as a
        # ubiquitous, non-discriminative corpus-wide word.
        {
            "Scientific_Name": "Noise plant one",
            "Evidence_Record_ID": 3,
            "Target_Indication": "Type 2 diabetes",
            "Primary_Outcome": "Improved fasting glucose in a randomized trial",
        },
        {
            "Scientific_Name": "Noise plant two",
            "Evidence_Record_ID": 4,
            "Target_Indication": "Insomnia",
            "Primary_Outcome": "Improved sleep latency in a randomized trial",
        },
        {
            "Scientific_Name": "Noise plant three",
            "Evidence_Record_ID": 5,
            "Target_Indication": "Migraine",
            "Primary_Outcome": "Reduced headache frequency in a randomized trial",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Fictus planta", "Known_Active_Compounds": "fictusol",
         "Known_Targets": "crosslinking", "Indications_Text": ""},
        {"Scientific_Name": "Noise plant one", "Known_Active_Compounds": "a", "Known_Targets": "ampk", "Indications_Text": ""},
        {"Scientific_Name": "Noise plant two", "Known_Active_Compounds": "b", "Known_Targets": "gaba", "Indications_Text": ""},
        {"Scientific_Name": "Noise plant three", "Known_Active_Compounds": "c", "Known_Targets": "cgrp", "Indications_Text": ""},
    ])
    raw = discover_indication_candidates(engine, _CORPUS_SEED_INDICATION, dosage_form="oral")
    assert "Fictus planta" in set(raw["Alternative_Plant"])

    fictus_rows = raw[raw["Alternative_Plant"] == "Fictus planta"]
    seed_rows = fictus_rows[fictus_rows["Indication_Match_Type"] == MATCH_EXACT_INDICATION]
    derived_rows = fictus_rows[fictus_rows["Indication_Match_Type"] == MATCH_CORPUS_DERIVED_SEMANTIC]

    assert not seed_rows.empty
    seed_row = seed_rows.iloc[0]

    # The second record receives bounded corpus-derived relevance...
    assert not derived_rows.empty
    derived_row = derived_rows.iloc[0]
    assert 0 < derived_row["Indication_Match_Score"] < 0.55

    # ...the reason identifies the derived term...
    assert "crosslinking" in derived_row["Indication_Match_Reason"].lower()

    # ...and it cannot independently dominate direct evidence: the seed
    # (exact) record scores strictly higher than the corpus-derived one.
    assert seed_row["Indication_Match_Score"] > derived_row["Indication_Match_Score"]


# ---------------------------------------------------------------------------
# 3. Negative-control test
# ---------------------------------------------------------------------------

def test_generic_shared_words_do_not_create_a_relevant_candidate():
    engine = _Engine([
        {
            "Scientific_Name": "Generic fictus",
            "Evidence_Record_ID": 1,
            "Target_Indication": "An unspecified ailment",
            "Study_Type": "Randomized human clinical trial",
            "Primary_Outcome": "This treatment showed an effect in patients using extract in a clinical study",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Generic fictus", "Known_Active_Compounds": "x",
         "Known_Targets": "y", "Indications_Text": ""},
    ])
    raw = discover_indication_candidates(engine, "a wholly different novel disorder xyzzyplex", dosage_form="oral")
    assert "Generic fictus" not in set(raw["Alternative_Plant"])


# ---------------------------------------------------------------------------
# 4. Real cough regression (no cough-specific hardcoding)
# ---------------------------------------------------------------------------

def test_cough_regression_via_corpus_evidence_no_hardcoded_cough_terms():
    engine = _Engine([
        {
            "Scientific_Name": "Thymus vulgaris",
            "Evidence_Record_ID": 1,
            "Target_Indication": "Acute bronchitis",
            "Primary_Outcome": "Demonstrated antitussive and expectorant activity in a randomized human trial",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Thymus vulgaris", "Known_Active_Compounds": "thymol",
         "Known_Targets": "expectorant", "Indications_Text": ""},
    ])
    raw = discover_indication_candidates(engine, "Cough", dosage_form="oral")
    assert "Thymus vulgaris" in set(raw["Alternative_Plant"])


# ---------------------------------------------------------------------------
# 5. Existing diabetes regression
# ---------------------------------------------------------------------------

def test_diabetes_regression_no_leakage_from_unrelated_plant():
    engine = _Engine([
        {
            "Scientific_Name": "Diabetes plant",
            "Evidence_Record_ID": 1,
            "Target_Indication": "Type 2 diabetes",
            "Primary_Outcome": "Reduced fasting blood glucose and improved HbA1c in a randomized trial",
        },
        {
            "Scientific_Name": "Unrelated plant",
            "Evidence_Record_ID": 2,
            "Target_Indication": "Cough",
            "Primary_Outcome": "Antitussive activity in a randomized trial",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Diabetes plant", "Known_Active_Compounds": "x",
         "Known_Targets": "ampk", "Indications_Text": ""},
        {"Scientific_Name": "Unrelated plant", "Known_Active_Compounds": "y",
         "Known_Targets": "expectorant", "Indications_Text": ""},
    ])
    raw = discover_indication_candidates(engine, "Type 2 diabetes", dosage_form="oral")
    assert "Diabetes plant" in set(raw["Alternative_Plant"])
    assert "Unrelated plant" not in set(raw["Alternative_Plant"])


# ---------------------------------------------------------------------------
# 6. Discovery/shortlist consistency -- no second recalculation
# ---------------------------------------------------------------------------

def test_shortlist_uses_authoritative_field_not_independent_recomputation():
    """Directly proves candidate_shortlisting.py does not recompute relevance
    from indication_semantics.py when the authoritative fields are present.

    Constructed so the row's actual narrative text contains nothing that the
    LEGACY (indication_semantics-based) path could match -- if the
    authoritative Indication_Match_Type field were ignored and relevance
    were independently recomputed, this would score 0. It does not, which
    proves the authoritative field is what drives the score.
    """
    from candidate_shortlisting import _indication_relevance_detail

    row = {
        "Alternative_Plant": "Fictus planta",
        "Indication_Match_Type": MATCH_EXACT_INDICATION,
        "Indication_Match_Score": 1.0,
        "Indication_Match_Terms": _UNSEEN_INDICATION,
        "Indication_Match_Reason": "Exact indication phrase matched",
        "Indication_Match_Confidence": 95.0,
        "Source_Record_IDs": "REC1",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human randomized controlled trial",
        # Deliberately empty: the legacy path's blob comes only from these
        # columns, and none of them contain anything indication_semantics.py
        # (or a bare-token match) could resolve.
        "Target_or_Mechanism": "",
        "Scientific_Rationale": "",
        "Clinical_Rationale": "",
        "Evidence_Strengths": "",
        "Evidence_Weaknesses": "",
        "Applicability_Summary": "",
    }
    group = pd.DataFrame([row])

    points, tier, mode, source_count = _indication_relevance_detail(group, _UNSEEN_INDICATION)
    assert points > 0
    assert tier != "No relevance"

    # Same group, with the authoritative column removed entirely: this now
    # exercises the legacy fallback, which (correctly) finds nothing, since
    # indication_semantics.py has no entry for this phrase and the narrative
    # blob is empty. This contrast is the proof that the authoritative path
    # above was not coincidentally getting the same answer from the fallback.
    group_without_authoritative = group.drop(columns=["Indication_Match_Type"])
    points2, tier2, _, _ = _indication_relevance_detail(group_without_authoritative, _UNSEEN_INDICATION)
    assert points2 == 0.0
    assert tier2 == "No relevance"


def test_discovery_and_shortlist_never_disagree_about_match_type_source():
    """End-to-end: the match_type recorded by discovery is the same value
    read (not recomputed) by shortlisting for every row of the relevant
    plant."""
    from candidate_shortlisting import _row_authoritative_relevance

    engine = _unseen_indication_engine()
    raw = discover_indication_candidates(engine, _UNSEEN_INDICATION, dosage_form="oral")
    fictus_rows = raw[raw["Alternative_Plant"] == "Fictus planta"]
    assert not fictus_rows.empty
    for _, row in fictus_rows.iterrows():
        match_type, _terms = _row_authoritative_relevance(row)
        assert match_type == row["Indication_Match_Type"]

# ---------------------------------------------------------------------------
# 7. Safety regression -- structured Ginkgo safety/interactions still survive
# ---------------------------------------------------------------------------

def test_ginkgo_safety_and_interaction_and_reassurance_survive_new_wiring():
    """Confirms the relevance-engine rewiring in this file did not regress
    the structured-safety fixes from the previous rounds (Safety_Flags,
    Interaction_Flags, Safety_Reassurance). Uses two separate records, as
    real Supabase evidence_records rows do (one adverse/interaction case
    report, one reassurance meta-analysis) -- combining both structured
    fields onto a single row hits an unrelated pre-existing quirk where
    _pick_from_row keeps only the first populated column of a priority list
    rather than merging them; see known-limitations notes."""
    engine = _Engine([
        {
            "Scientific_Name": "Ginkgo biloba",
            "Evidence_Record_ID": 900,
            "Adverse_Events": [
                {"event": "fatal breakthrough seizure"},
                {"event": "spontaneous hyphema"},
            ],
            "Interactions_Structured": [{
                "interacting_class": "anticonvulsants",
                "drugs": ["phenytoin", "valproate"],
                "mechanism": "CYP2C19 induction",
            }],
        },
        {
            "Scientific_Name": "Ginkgo biloba",
            "Evidence_Record_ID": 901,
            "Safety_Findings": "No important safety concerns with EGb761 at 240 mg/day",
        },
    ])
    engine.set_candidates([{
        "Scientific_Name": "Ginkgo biloba",
        "Known_Active_Compounds": "ginkgolide B",
        "Known_Targets": "platelet activating factor",
        "Indications_Text": "cognitive decline",
    }])
    out = discover_indication_candidates(engine, "cognitive decline", dosage_form="oral")
    assert not out.empty
    row = out.iloc[0]
    assert "fatal breakthrough seizure" in row["Safety_Flags"]
    assert "spontaneous hyphema" in row["Safety_Flags"]
    interaction_text = row["Interaction_Flags"].lower()
    assert "phenytoin" in interaction_text or "anticonvulsant" in interaction_text
    assert "no important safety concerns" in row["Safety_Reassurance"].lower()




def test_compound_source_mode_rows_use_legacy_fallback_unaffected():
    """Rows without Indication_Match_Type (as compound-source discovery mode
    produces, since it never calls discover_indication_candidates) must
    still be scored via the pre-existing indication_semantics.py fallback,
    unchanged."""
    from candidate_shortlisting import build_plant_candidate_shortlist

    df = pd.DataFrame([{
        "Reference_Plant": "Reference plant",
        "Alternative_Plant": "Candidate plant",
        "Shared_or_Similar_Compound": "specific alkaloid",
        "Novelty_Status": "Rare / differentiating",
        "Target_or_Mechanism": "insulin resistance",
        "Target_Provenance": "Supported by source record",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human clinical evidence",
        "Candidate_Evidence_Strength_Tier": "Direct evidence",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": "PMID:123",
        "Scientific_Rationale": "type 2 diabetes glycemic control",
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "Regulatory_Barriers": "None identified",
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "Investigate",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "R&D_Opportunity_Score": 70,
        # No Indication_Match_Type column at all -- simulates compound-source mode.
    }])
    summary, audit = build_plant_candidate_shortlist(df, indication="Type 2 diabetes", dosage_form="Infusion")
    assert "Indication_Match_Type" not in audit.columns
    assert len(summary) == 1
    # Legacy path still resolves "type 2 diabetes" via indication_semantics.py.
    assert summary.iloc[0]["Indication_Relevance_Score"] > 0
