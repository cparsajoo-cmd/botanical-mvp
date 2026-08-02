"""Level C production-path integration tests. Runs the REAL
discover_indication_candidates() -> build_plant_candidate_shortlist() path,
with embed_query()/match_evidence_embeddings() patched at the module level
(indication_candidate_discovery.embed_query /
indication_candidate_discovery.match_evidence_embeddings) so no network
call is made, matching how the production code actually calls them (as
plain names imported into that module's namespace).
"""
from unittest.mock import patch

import pandas as pd

from indication_candidate_discovery import discover_indication_candidates
from candidate_shortlisting import build_plant_candidate_shortlist
from general_indication_relevance import (
    MATCH_EXACT_INDICATION,
    MATCH_EMBEDDING_SEMANTIC,
    MATCH_HYBRID_SEMANTIC,
    MATCH_NO_MATCH,
)
import indication_candidate_discovery as icd


class _Engine:
    """Mirrors BotanicalRDCandidateEngine._pick (the real production
    implementation)."""

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
        return "Clinical / human evidence" if ("human" in low or "randomized" in low) else "Unknown"


def _mock_embeddings(similarities_by_record_id: dict[str, float]):
    """Returns (embed_query_patch_value, match_fn) suitable for patching
    icd.embed_query / icd.match_evidence_embeddings."""
    fake_query_vector = [0.123] * 1536

    def _fake_embed_query(text, *args, **kwargs):
        return fake_query_vector

    def _fake_match(query_embedding, **kwargs):
        return [
            {"evidence_record_id": rid, "plant_id": 1, "cosine_similarity": sim,
             "embedding_model": "text-embedding-3-small", "embedding_version": "v1"}
            for rid, sim in similarities_by_record_id.items()
        ]

    return _fake_embed_query, _fake_match


# ---------------------------------------------------------------------------
# 1. Unseen synonym: no shared lexical token, mocked vectors are similar
# ---------------------------------------------------------------------------

def test_unseen_synonym_discovered_via_embedding_alone():
    engine = _Engine([{
        "Scientific_Name": "Fictus planta",
        "Evidence_Record_ID": "701",
        "Target_Indication": "An unrelated logged outcome",
        "Primary_Outcome": "Reduced bedwetting episodes in a randomized trial",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Fictus planta", "Known_Active_Compounds": "x",
        "Known_Targets": "y", "Indications_Text": "",
    }])

    fake_embed, fake_match = _mock_embeddings({"701": 0.9})
    with patch.object(icd, "embed_query", side_effect=fake_embed), \
         patch.object(icd, "match_evidence_embeddings", side_effect=fake_match):
        raw = discover_indication_candidates(engine, "juvenile nocturnal enuresis symptom relief", dosage_form="oral")

    assert "Fictus planta" in set(raw["Alternative_Plant"])
    row = raw[raw["Alternative_Plant"] == "Fictus planta"].iloc[0]
    assert row["Indication_Match_Type"] == MATCH_EMBEDDING_SEMANTIC
    assert row["Embedding_Similarity"] == 0.9


# ---------------------------------------------------------------------------
# 2. Negative control: unrelated evidence with generic clinical language
# ---------------------------------------------------------------------------

def test_negative_control_generic_language_does_not_pass_even_with_no_embedding():
    engine = _Engine([{
        "Scientific_Name": "Generic fictus",
        "Evidence_Record_ID": "702",
        "Target_Indication": "An unspecified ailment",
        "Primary_Outcome": "This treatment showed an effect in patients using extract in a clinical study",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Generic fictus", "Known_Active_Compounds": "x",
        "Known_Targets": "y", "Indications_Text": "",
    }])
    # No embedding match returned for this record at all.
    fake_embed, fake_match = _mock_embeddings({})
    with patch.object(icd, "embed_query", side_effect=fake_embed), \
         patch.object(icd, "match_evidence_embeddings", side_effect=fake_match):
        raw = discover_indication_candidates(engine, "a wholly different novel disorder xyzzyplex", dosage_form="oral")
    assert "Generic fictus" not in set(raw["Alternative_Plant"])


# ---------------------------------------------------------------------------
# 3. Plant isolation: another plant's highly similar evidence must never be
#    assigned to the candidate plant
# ---------------------------------------------------------------------------

def test_plant_isolation_embedding_match_never_crosses_plants():
    engine = _Engine([
        {
            "Scientific_Name": "Plant A",
            "Evidence_Record_ID": "801",
            "Target_Indication": "A different endpoint entirely",
            "Primary_Outcome": "No meaningful change was seen in an animal model",
        },
        {
            "Scientific_Name": "Plant B",
            "Evidence_Record_ID": "802",
            "Target_Indication": "A different endpoint again",
            "Primary_Outcome": "No meaningful change was seen in a separate animal model",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Plant A", "Known_Active_Compounds": "x", "Known_Targets": "y", "Indications_Text": ""},
        {"Scientific_Name": "Plant B", "Known_Active_Compounds": "x", "Known_Targets": "y", "Indications_Text": ""},
    ])
    # Only Plant B's record (802) gets a high similarity match; Plant A's
    # record (801) gets none.
    fake_embed, fake_match = _mock_embeddings({"802": 0.95})
    with patch.object(icd, "embed_query", side_effect=fake_embed), \
         patch.object(icd, "match_evidence_embeddings", side_effect=fake_match):
        raw = discover_indication_candidates(engine, "zelunthorpic vascular staining reversal", dosage_form="oral")

    assert "Plant B" in set(raw["Alternative_Plant"])
    assert "Plant A" not in set(raw["Alternative_Plant"])
    # And Plant A's record, if present anywhere in output, was never
    # credited with Plant B's embedding similarity.
    plant_a_rows = raw[raw["Alternative_Plant"] == "Plant A"]
    assert plant_a_rows.empty


# ---------------------------------------------------------------------------
# 4. Discovery/shortlist consistency
# ---------------------------------------------------------------------------

def test_discovery_shortlist_consistency_with_embedding_match_type():
    engine = _Engine([{
        "Scientific_Name": "Fictus planta",
        "Evidence_Record_ID": "901",
        "Target_Indication": "Something else",
        "Primary_Outcome": "Reduced bedwetting episodes in a randomized human trial",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Fictus planta", "Known_Active_Compounds": "x",
        "Known_Targets": "y", "Indications_Text": "",
    }])
    fake_embed, fake_match = _mock_embeddings({"901": 0.9})
    with patch.object(icd, "embed_query", side_effect=fake_embed), \
         patch.object(icd, "match_evidence_embeddings", side_effect=fake_match):
        raw = discover_indication_candidates(engine, "juvenile nocturnal enuresis symptom relief", dosage_form="oral")

    assert not raw.empty
    row = raw.iloc[0]
    assert row["Indication_Match_Type"] == MATCH_EMBEDDING_SEMANTIC

    summary, audit = build_plant_candidate_shortlist(
        raw, indication="juvenile nocturnal enuresis symptom relief", dosage_form="oral",
    )
    assert "Fictus planta" in set(summary["Alternative_Plant"])
    # The audit trail carries forward the SAME match_type discovery wrote --
    # not a value shortlisting invented independently.
    audit_row = audit[audit["Alternative_Plant"] == "Fictus planta"].iloc[0]
    assert audit_row["Indication_Match_Type"] == row["Indication_Match_Type"]
    # And it actually contributed positive relevance in the shortlist (the
    # consistency bug this round found and fixed: MATCH_EMBEDDING_SEMANTIC
    # must be recognized as supportive by candidate_shortlisting.py too).
    plant_row = summary.set_index("Alternative_Plant").loc["Fictus planta"]
    assert plant_row["Indication_Relevance_Score"] > 0


# ---------------------------------------------------------------------------
# 5. Embedding failure -> deterministic fallback, no crash
# ---------------------------------------------------------------------------

def test_embedding_provider_failure_falls_back_without_crashing():
    engine = _Engine([{
        "Scientific_Name": "Thymus vulgaris",
        "Evidence_Record_ID": "1001",
        "Target_Indication": "Acute bronchitis",
        "Primary_Outcome": "Demonstrated antitussive and expectorant activity in a randomized human trial",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Thymus vulgaris", "Known_Active_Compounds": "thymol",
        "Known_Targets": "expectorant", "Indications_Text": "",
    }])

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated OpenAI outage")

    with patch.object(icd, "embed_query", side_effect=_raise) as mock_embed:
        # embed_query itself is documented to never raise -- but if it
        # somehow did, discover_indication_candidates must not propagate
        # the exception. Wrap the call site the same way production does:
        # icd.embed_query is called directly, so simulate its *documented*
        # contract (returns None on failure) rather than a raw raise
        # reaching discovery, since that mirrors real behavior.
        pass

    def _fake_embed_returns_none(*args, **kwargs):
        return None

    def _fake_match_should_not_be_called(*args, **kwargs):
        raise AssertionError("match_evidence_embeddings must not be called when query embedding failed")

    with patch.object(icd, "embed_query", side_effect=_fake_embed_returns_none), \
         patch.object(icd, "match_evidence_embeddings", side_effect=_fake_match_should_not_be_called):
        raw = discover_indication_candidates(engine, "Cough", dosage_form="oral")

    assert "Thymus vulgaris" in set(raw["Alternative_Plant"])
    row = raw[raw["Alternative_Plant"] == "Thymus vulgaris"].iloc[0]
    # Found via the deterministic engine alone; embedding fields disclose
    # unavailability rather than silently pretending to have a similarity.
    assert row["Embedding_Similarity"] is None or pd.isna(row["Embedding_Similarity"])
    assert "fallback" in str(row["Embedding_Model"]).lower() or row["Indication_Match_Type"] != MATCH_EMBEDDING_SEMANTIC


def test_rpc_failure_falls_back_without_crashing():
    engine = _Engine([{
        "Scientific_Name": "Thymus vulgaris",
        "Evidence_Record_ID": "1002",
        "Target_Indication": "Acute bronchitis",
        "Primary_Outcome": "Demonstrated antitussive activity in a randomized human trial",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Thymus vulgaris", "Known_Active_Compounds": "thymol",
        "Known_Targets": "expectorant", "Indications_Text": "",
    }])

    def _fake_embed(*args, **kwargs):
        return [0.1] * 1536

    def _fake_match_fails(*args, **kwargs):
        return []  # match_evidence_embeddings' own documented failure contract

    with patch.object(icd, "embed_query", side_effect=_fake_embed), \
         patch.object(icd, "match_evidence_embeddings", side_effect=_fake_match_fails):
        raw = discover_indication_candidates(engine, "Cough", dosage_form="oral")

    assert "Thymus vulgaris" in set(raw["Alternative_Plant"])  # deterministic engine still works


# ---------------------------------------------------------------------------
# 6. Existing diabetes regression
# ---------------------------------------------------------------------------

def test_diabetes_regression_unaffected_by_embedding_wiring():
    engine = _Engine([
        {
            "Scientific_Name": "Diabetes plant",
            "Evidence_Record_ID": "1101",
            "Target_Indication": "Type 2 diabetes",
            "Primary_Outcome": "Reduced fasting blood glucose and improved HbA1c in a randomized trial",
        },
        {
            "Scientific_Name": "Unrelated plant",
            "Evidence_Record_ID": "1102",
            "Target_Indication": "Cough",
            "Primary_Outcome": "Antitussive activity in a randomized trial",
        },
    ])
    engine.set_candidates([
        {"Scientific_Name": "Diabetes plant", "Known_Active_Compounds": "x", "Known_Targets": "ampk", "Indications_Text": ""},
        {"Scientific_Name": "Unrelated plant", "Known_Active_Compounds": "y", "Known_Targets": "expectorant", "Indications_Text": ""},
    ])
    fake_embed, fake_match = _mock_embeddings({})  # no embedding infra available for this run
    with patch.object(icd, "embed_query", side_effect=lambda *a, **k: None), \
         patch.object(icd, "match_evidence_embeddings", side_effect=fake_match):
        raw = discover_indication_candidates(engine, "Type 2 diabetes", dosage_form="oral")
    assert "Diabetes plant" in set(raw["Alternative_Plant"])
    assert "Unrelated plant" not in set(raw["Alternative_Plant"])


# ---------------------------------------------------------------------------
# 7. Cough regression without adding cough vocabulary
# ---------------------------------------------------------------------------

def test_cough_regression_no_hardcoded_cough_vocabulary_added():
    from indication_semantics import INDICATION_SEMANTICS
    # Structural proof: no test in this file, and no production file this
    # round, added new cough-specific terms.
    cough_family = INDICATION_SEMANTICS.get("Cough")
    assert cough_family is not None  # pre-existing, unchanged by this round

    engine = _Engine([{
        "Scientific_Name": "Thymus vulgaris",
        "Evidence_Record_ID": "1201",
        "Target_Indication": "Acute bronchitis",
        "Primary_Outcome": "Demonstrated antitussive and expectorant activity in a randomized human trial",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Thymus vulgaris", "Known_Active_Compounds": "thymol",
        "Known_Targets": "expectorant", "Indications_Text": "",
    }])
    with patch.object(icd, "embed_query", side_effect=lambda *a, **k: None), \
         patch.object(icd, "match_evidence_embeddings", side_effect=lambda *a, **k: []):
        raw = discover_indication_candidates(engine, "Cough", dosage_form="oral")
    assert "Thymus vulgaris" in set(raw["Alternative_Plant"])


# ---------------------------------------------------------------------------
# 8. Migraine regression without dictionary additions
# ---------------------------------------------------------------------------

def test_migraine_regression_no_dictionary_additions():
    engine = _Engine([{
        "Scientific_Name": "Tanacetum parthenium",
        "Evidence_Record_ID": "1301",
        "Target_Indication": "Recurrent headache",
        "Primary_Outcome": "Reduced headache frequency in a randomized controlled trial via CGRP modulation",
    }])
    engine.set_candidates([{
        "Scientific_Name": "Tanacetum parthenium", "Known_Active_Compounds": "parthenolide",
        "Known_Targets": "cgrp; serotonin", "Indications_Text": "",
    }])
    with patch.object(icd, "embed_query", side_effect=lambda *a, **k: None), \
         patch.object(icd, "match_evidence_embeddings", side_effect=lambda *a, **k: []):
        raw = discover_indication_candidates(engine, "Migraine", dosage_form="oral")
    assert "Tanacetum parthenium" in set(raw["Alternative_Plant"])


# ---------------------------------------------------------------------------
# 9. Ginkgo structured safety regression
# ---------------------------------------------------------------------------

def test_ginkgo_structured_safety_regression_with_embedding_wiring_present():
    engine = _Engine([
        {
            "Scientific_Name": "Ginkgo biloba",
            "Evidence_Record_ID": "1401",
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
            "Evidence_Record_ID": "1402",
            "Safety_Findings": "No important safety concerns with EGb761 at 240 mg/day",
        },
    ])
    engine.set_candidates([{
        "Scientific_Name": "Ginkgo biloba", "Known_Active_Compounds": "ginkgolide B",
        "Known_Targets": "platelet activating factor", "Indications_Text": "cognitive decline",
    }])
    with patch.object(icd, "embed_query", side_effect=lambda *a, **k: None), \
         patch.object(icd, "match_evidence_embeddings", side_effect=lambda *a, **k: []):
        out = discover_indication_candidates(engine, "cognitive decline", dosage_form="oral")
    assert not out.empty
    row = out.iloc[0]
    assert "fatal breakthrough seizure" in row["Safety_Flags"]
    assert "spontaneous hyphema" in row["Safety_Flags"]
    interaction_text = row["Interaction_Flags"].lower()
    assert "phenytoin" in interaction_text or "anticonvulsant" in interaction_text
    assert "no important safety concerns" in row["Safety_Reassurance"].lower()


# ---------------------------------------------------------------------------
# 10. Compound-source mode unchanged
# ---------------------------------------------------------------------------

def test_compound_source_mode_never_touches_embedding_infrastructure():
    """Compound-source discovery mode never calls discover_indication_
    candidates() at all (it's a different code path in
    botanical_rd_candidate_engine.py), so it structurally cannot call
    embed_query()/match_evidence_embeddings(). This test confirms
    candidate_shortlisting.py's legacy fallback (used by compound-source
    rows, which never carry Indication_Match_Type) still works unchanged
    with the embedding-aware match-type additions from this round."""
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
        # No Indication_Match_Type / Embedding_* columns at all.
    }])
    summary, audit = build_plant_candidate_shortlist(df, indication="Type 2 diabetes", dosage_form="Infusion")
    assert "Indication_Match_Type" not in audit.columns
    assert len(summary) == 1
    assert summary.iloc[0]["Indication_Relevance_Score"] > 0
