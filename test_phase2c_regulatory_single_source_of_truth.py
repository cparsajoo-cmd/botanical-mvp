"""Phase 2C regression suite — regulatory single-source-of-truth cleanup.

Confirms:
1. evidence_extractor.py / evidence_standardizer.py no longer produce
   EMA_Status regulatory conclusions from keyword or LLM text-mention
   detection — only the Regulatory_Reference_Detected annotation.
2. source_ingestion_engine.py's STANDARD_FIELDS allowlist actually
   preserves that annotation (rather than silently dropping it, the
   way Evidence_Level once was).
3. GLOBAL_PLANT_CANDIDATES's hardcoded EMA_Status values are
   neutralized at the one point they enter
   botanical_rd_candidate_engine.py's candidate-data pipeline
   (_candidate_frame()), WITHOUT altering global_candidate_ranking_
   engine.py's separate, still-protected ranking pipeline, which reads
   the same underlying data directly.
4. structured_rationale.build_regulatory_intelligence() prefers the
   canonical EMA_HMPC_Match_Category over its own string interpretation
   when supplied, while remaining backward-compatible for callers that
   don't pass it yet.

All fixtures are synthetic/generic — no plant name is load-bearing to
any assertion below.
"""

import pytest

from evidence_extractor import extract_evidence_from_text
from evidence_standardizer import standardize_extracted_record
from source_ingestion_engine import STANDARD_FIELDS, create_empty_evidence_record, normalize_source_record


# ---------------------------------------------------------------------
# 1. evidence_extractor.py — annotation only, never a regulatory status.
# ---------------------------------------------------------------------

def test_ema_mention_never_sets_ema_status():
    record = extract_evidence_from_text(
        "A review of EMA and HMPC committee activity for herbal substances."
    )
    assert record["EMA_Status"] == ""
    assert record["Regulatory_Reference_Detected"] is True


def test_no_ema_mention_leaves_annotation_false():
    record = extract_evidence_from_text("A study about an unrelated topic entirely.")
    assert record["Regulatory_Reference_Detected"] is False
    assert record["EMA_Status"] == ""


def test_regulatory_status_field_no_longer_set_by_keyword_detection():
    record = extract_evidence_from_text("European Medicines Agency (EMA) mentioned here.")
    assert record["Regulatory_Status"] == ""


# ---------------------------------------------------------------------
# 2. evidence_standardizer.py — LLM ema_relevance -> annotation only.
# ---------------------------------------------------------------------

def test_llm_ema_relevance_never_sets_ema_status(monkeypatch):
    import evidence_standardizer as es_mod

    def fake_llm(text, selected_dosage_form="", selected_indication=""):
        return {"ema_relevance": "yes", "who_relevance": "yes", "escop_relevance": "no"}

    monkeypatch.setattr(es_mod, "extract_evidence_with_llm", fake_llm)

    extracted = {"Notes": "some publication text", "Source_Type": "PubMed"}
    result = standardize_extracted_record(extracted, {"source_type": "PubMed"})

    assert result["EMA_Status"] != "Yes"
    assert result["Regulatory_Reference_Detected"] is True
    # WHO/ESCOP are unaffected by this phase's scope (no canonical
    # connector exists for them yet) — still the pre-existing behavior.
    assert result["WHO_Status"] == "Yes"
    assert result["ESCOP_Status"] == ""


def test_llm_ema_relevance_no_leaves_annotation_false(monkeypatch):
    import evidence_standardizer as es_mod

    def fake_llm(text, selected_dosage_form="", selected_indication=""):
        return {"ema_relevance": "no"}

    monkeypatch.setattr(es_mod, "extract_evidence_with_llm", fake_llm)

    extracted = {"Notes": "unrelated text", "Source_Type": "PubMed"}
    result = standardize_extracted_record(extracted, {"source_type": "PubMed"})
    assert result["Regulatory_Reference_Detected"] is False


# ---------------------------------------------------------------------
# 3. source_ingestion_engine.py — annotation survives normalization.
# ---------------------------------------------------------------------

def test_standard_fields_includes_regulatory_reference_detected():
    assert "Regulatory_Reference_Detected" in STANDARD_FIELDS
    assert STANDARD_FIELDS["Regulatory_Reference_Detected"] is False


def test_create_empty_evidence_record_defaults_annotation_false():
    record = create_empty_evidence_record()
    assert record["Regulatory_Reference_Detected"] is False


def test_normalize_source_record_preserves_the_annotation():
    raw = {"Scientific_Name": "Genusia speciosa", "Regulatory_Reference_Detected": True}
    normalized = normalize_source_record(raw)
    assert normalized["Regulatory_Reference_Detected"] is True


def test_normalize_source_record_does_not_smuggle_in_ema_status_yes():
    # Even if some upstream dict still had the old-style value (e.g.
    # from an un-migrated caller), normalize_source_record's allowlist
    # behavior for EMA_Status itself is unchanged — this test exists to
    # make explicit that Phase 2C did not touch that pass-through, only
    # added the new annotation field alongside it.
    raw = {"Scientific_Name": "Genusia speciosa", "EMA_Status": "Yes"}
    normalized = normalize_source_record(raw)
    assert normalized["EMA_Status"] == "Yes"  # unchanged pass-through behavior
    assert normalized["Regulatory_Reference_Detected"] is False  # not smuggled in


# ---------------------------------------------------------------------
# 4. GLOBAL_PLANT_CANDIDATES neutralization at the engine boundary.
# ---------------------------------------------------------------------

def test_candidate_frame_neutralizes_hardcoded_ema_status():
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine

    engine = BotanicalRDCandidateEngine.__new__(BotanicalRDCandidateEngine)
    engine.candidate_data = [
        {
            "Scientific_Name": "Genusia speciosa",
            "Common_Name": "",
            "Known_Active_Compounds": ["compoundia"],
            "Known_Targets": ["targetia"],
            "Indications": ["Testicular indication"],
            "EMA_Status": "Yes",
        }
    ]
    frame = engine._candidate_frame()
    assert frame.iloc[0]["EMA_Status"] == ""


def test_candidate_frame_neutralizes_ema_status_no_too():
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine

    engine = BotanicalRDCandidateEngine.__new__(BotanicalRDCandidateEngine)
    engine.candidate_data = [
        {
            "Scientific_Name": "Genusia negativa",
            "Known_Active_Compounds": [],
            "Known_Targets": [],
            "Indications": [],
            "EMA_Status": "No",
        }
    ]
    frame = engine._candidate_frame()
    assert frame.iloc[0]["EMA_Status"] == ""


def test_global_plant_candidates_data_file_itself_is_untouched():
    # Rule 3/5 compliance check: the underlying GLOBAL_PLANT_CANDIDATES
    # list must still carry its original EMA_Status values — this
    # phase neutralizes them only at the botanical_rd_candidate_engine
    # boundary, never by editing the shared data source, because
    # global_candidate_ranking_engine.py's separate (protected)
    # candidate-ranking pipeline reads that same source directly.
    from global_plant_candidate_database import GLOBAL_PLANT_CANDIDATES

    valerian = next(
        c for c in GLOBAL_PLANT_CANDIDATES if c["Scientific_Name"] == "Valeriana officinalis"
    )
    assert valerian["EMA_Status"] == "Yes"


def test_global_candidate_ranking_engine_regulatory_score_unaffected():
    # Rule 5 compliance: the separate ranking pipeline's own scoring of
    # GLOBAL_PLANT_CANDIDATES data must be byte-for-byte unchanged by
    # this phase.
    from global_candidate_ranking_engine import _regulatory_score

    listed = _regulatory_score({"EMA_Status": "Yes"}, market="European Union")
    not_listed = _regulatory_score({"EMA_Status": "No"}, market="European Union")
    assert listed != not_listed  # still a real, varying signal in this pipeline


def test_market_status_never_reflects_hardcoded_candidate_data_ema_status():
    # End-to-end proof for item 1: a candidate row carrying the
    # hardcoded "Yes" must not cause _market_status() to report
    # anything resembling "Listed" purely because of that hardcode.
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine

    engine = BotanicalRDCandidateEngine.__new__(BotanicalRDCandidateEngine)
    engine.candidate_data = [
        {
            "Scientific_Name": "Genusia speciosa",
            "Known_Active_Compounds": [],
            "Known_Targets": [],
            "Indications": [],
            "EMA_Status": "Yes",
        }
    ]
    frame = engine._candidate_frame()
    alt_row = frame.iloc[0]
    engine.use_live_search = False
    result = engine._market_status(alt=alt_row, evidence="", market="EU")
    assert result not in ("Regulatory monograph exists", "Listed in EMA HMPC inventory — monograph not established")


# ---------------------------------------------------------------------
# 5. structured_rationale.py — consumes EMA_HMPC_Match_Category.
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "category,expected_substring",
    [
        ("exact_species_match", "Present in EMA HMPC inventory"),
        ("genus_only_match", "Genus present in EMA HMPC inventory"),
        ("related_species_only", "different species of the same genus"),
        ("ambiguous_match", "Conflicting inventory signals"),
        ("searched_not_found", "Not found in EMA HMPC inventory"),
        ("source_unavailable", "Not available"),
        ("parsing_failed", "Not available"),
    ],
)
def test_build_regulatory_intelligence_prefers_match_category(category, expected_substring):
    from structured_rationale import build_regulatory_intelligence

    obj = build_regulatory_intelligence(
        market_landscape_ema_status="some arbitrary string that should be ignored",
        market_landscape_regulatory_source=None,
        regulatory_barriers=None,
        market_status=None,
        market="European Union",
        market_landscape_ema_match_category=category,
    )
    assert expected_substring in obj["ema_status"]


def test_build_regulatory_intelligence_falls_back_without_category():
    from structured_rationale import build_regulatory_intelligence

    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None,
        market_status=None,
        market="European Union",
    )
    assert "Present in EMA HMPC inventory" in obj["ema_status"]


def test_build_regulatory_intelligence_distinguishes_genus_only_from_exact_match():
    from structured_rationale import build_regulatory_intelligence

    exact = build_regulatory_intelligence(
        market_landscape_ema_status=None, market_landscape_regulatory_source=None,
        regulatory_barriers=None, market_status=None, market="European Union",
        market_landscape_ema_match_category="exact_species_match",
    )
    genus_only = build_regulatory_intelligence(
        market_landscape_ema_status=None, market_landscape_regulatory_source=None,
        regulatory_barriers=None, market_status=None, market="European Union",
        market_landscape_ema_match_category="genus_only_match",
    )
    assert exact["ema_status"] != genus_only["ema_status"]
    assert "not confirmed" in genus_only["ema_status"]
