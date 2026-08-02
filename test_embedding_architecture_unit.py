"""Level A unit tests for the embedding/hybrid-relevance architecture.

Covers: canonical embedding text, deterministic hashing, exclusion of
safety-only text from efficacy text, exclusion of proxy/marketing records,
hybrid score components, fallback mode. No network calls anywhere in this
file -- everything here is a pure function.
"""
from evidence_embedding_text import (
    build_evidence_embedding_text,
    compute_content_hash,
    is_proxy_or_excluded_record,
)
from general_indication_relevance import (
    build_indication_profile,
    score_record_relevance_hybrid,
    MATCH_EXACT_INDICATION,
    MATCH_EXPLICIT_FIELD_OVERLAP,
    MATCH_HYBRID_SEMANTIC,
    MATCH_EMBEDDING_SEMANTIC,
    MATCH_CORPUS_DERIVED_SEMANTIC,
    MATCH_NO_MATCH,
    EMBEDDING_MIN_CONTRIBUTION,
    EMBEDDING_SEMANTIC_THRESHOLD,
    HYBRID_SEMANTIC_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Canonical embedding text
# ---------------------------------------------------------------------------

def test_canonical_embedding_text_includes_labeled_fields():
    record = {
        "plant_name": "Thymus vulgaris",
        "tier1_text": "Acute bronchitis",
        "tier2_text": "Reduced cough frequency",
        "study_type": "Randomized human clinical trial",
        "evidence_level": "Human RCT",
        "preparation": "Infusion",
        "tier3_text": "Antitussive activity demonstrated",
    }
    text = build_evidence_embedding_text(record)
    assert "Plant: Thymus vulgaris" in text
    assert "Indication: Acute bronchitis" in text
    assert "Outcome/Mechanism: Reduced cough frequency" in text
    assert "Study type: Randomized human clinical trial" in text
    assert "Preparation: Infusion" in text
    assert "Source text: Antitussive activity demonstrated" in text


def test_canonical_embedding_text_omits_empty_and_placeholder_fields():
    record = {
        "plant_name": "Thymus vulgaris",
        "tier1_text": "",
        "tier2_text": "unknown",
        "study_type": None,
        "tier3_text": "nan",
    }
    text = build_evidence_embedding_text(record)
    assert "Indication:" not in text
    assert "Outcome/Mechanism:" not in text
    assert "Study type:" not in text
    assert "Source text:" not in text
    assert text == "Plant: Thymus vulgaris"


def test_canonical_embedding_text_excludes_safety_fields():
    """Adverse_Events/Interactions_Structured/Safety_Findings passed in the
    record dict must have zero effect -- the function does not read those
    keys at all, so structured safety data can never independently create
    efficacy relevance."""
    record = {
        "plant_name": "Ginkgo biloba",
        "tier1_text": "Cognitive decline",
        "adverse_events": [{"event": "fatal breakthrough seizure"}],
        "interactions_structured": [{"drugs": ["phenytoin"]}],
        "safety_findings": "No important safety concerns with EGb761",
    }
    text = build_evidence_embedding_text(record)
    assert "seizure" not in text.lower()
    assert "phenytoin" not in text.lower()
    assert "safety concerns" not in text.lower()
    assert "Cognitive decline" in text


def test_canonical_embedding_text_deterministic_across_calls():
    record = {"plant_name": "Ginkgo biloba", "tier1_text": "Cognitive decline"}
    assert build_evidence_embedding_text(record) == build_evidence_embedding_text(dict(record))


# ---------------------------------------------------------------------------
# Deterministic hash
# ---------------------------------------------------------------------------

def test_content_hash_is_deterministic_and_sensitive_to_content():
    text_a = "Plant: Ginkgo biloba\nIndication: Cognitive decline"
    text_b = "Plant: Ginkgo biloba\nIndication: Cognitive decline"
    text_c = "Plant: Ginkgo biloba\nIndication: Diabetes"
    assert compute_content_hash(text_a) == compute_content_hash(text_b)
    assert compute_content_hash(text_a) != compute_content_hash(text_c)


def test_content_hash_is_a_hex_sha256():
    h = compute_content_hash("some text")
    assert len(h) == 64
    int(h, 16)  # raises ValueError if not valid hex


# ---------------------------------------------------------------------------
# Exclusion of proxy/marketing/ontology records
# ---------------------------------------------------------------------------

def test_chebi_records_excluded():
    assert is_proxy_or_excluded_record("ChEBI", "") is True


def test_patent_records_excluded():
    assert is_proxy_or_excluded_record("Patent/Literature", "") is True


def test_dailymed_records_excluded():
    assert is_proxy_or_excluded_record("DailyMed", "") is True


def test_chemical_composition_evidence_type_excluded():
    assert is_proxy_or_excluded_record("", "Chemical composition") is True


def test_genuine_clinical_source_not_excluded():
    assert is_proxy_or_excluded_record("PubMed", "Human RCT") is False


def test_excluded_record_produces_empty_embedding_text():
    record = {
        "plant_name": "Ginkgo biloba",
        "tier1_text": "Cognitive decline",
        "source_type": "ChEBI",
    }
    assert build_evidence_embedding_text(record) == ""


# ---------------------------------------------------------------------------
# Hybrid score components
# ---------------------------------------------------------------------------

def _profile_for(query: str, corpus: list[str]):
    return build_indication_profile(query, corpus)


def test_hybrid_tier1_exact_match_wins_regardless_of_embedding():
    profile = _profile_for("cough", ["cough treatment records"])
    result = score_record_relevance_hybrid(
        profile, tier1_text="cough", tier2_text="", tier3_text="",
        embedding_similarity=0.99,
    )
    assert result.match_type == MATCH_EXACT_INDICATION
    assert result.final_relevance_score == 1.0


def test_hybrid_embedding_alone_never_labelled_direct_evidence():
    """Rule 2: high embedding similarity alone cannot be labelled direct
    evidence -- it must be embedding_semantic or hybrid_semantic."""
    profile = _profile_for("chronic dry cough", ["unrelated corpus text about something else"])
    result = score_record_relevance_hybrid(
        profile, tier1_text="", tier2_text="", tier3_text="",
        embedding_similarity=0.95,
    )
    assert result.match_type not in (MATCH_EXACT_INDICATION, MATCH_EXPLICIT_FIELD_OVERLAP)
    assert result.match_type == MATCH_EMBEDDING_SEMANTIC


def test_hybrid_low_embedding_similarity_contributes_nothing():
    profile = _profile_for("chronic dry cough", ["unrelated corpus text"])
    result = score_record_relevance_hybrid(
        profile, tier1_text="", tier2_text="", tier3_text="",
        embedding_similarity=EMBEDDING_MIN_CONTRIBUTION - 0.1,
    )
    assert result.match_type == MATCH_NO_MATCH
    assert result.final_relevance_score == 0.0


def test_hybrid_score_exposes_all_component_fields():
    profile = _profile_for("cough", ["cough antitussive"])
    result = score_record_relevance_hybrid(
        profile, tier1_text="cough", tier2_text="", tier3_text="",
        embedding_similarity=0.7,
    )
    assert hasattr(result, "explicit_indication_score")
    assert hasattr(result, "embedding_similarity")
    assert hasattr(result, "outcome_mechanism_score")
    assert hasattr(result, "lexical_fallback_score")
    assert result.embedding_similarity == 0.7


def test_hybrid_embedding_never_alone_meets_exact_indication_bar():
    """Generic semantic similarity (no explicit field, no deterministic
    support) is capped well below 1.0 even at very high similarity."""
    profile = _profile_for("a wholly synthetic query term", ["unrelated corpus"])
    result = score_record_relevance_hybrid(
        profile, tier1_text="", tier2_text="", tier3_text="",
        embedding_similarity=0.999,
    )
    assert result.final_relevance_score < 1.0
    assert result.match_type == MATCH_EMBEDDING_SEMANTIC


# ---------------------------------------------------------------------------
# Fallback mode
# ---------------------------------------------------------------------------

def test_fallback_mode_true_when_embedding_similarity_is_none():
    profile = _profile_for("cough", ["cough treatment records"])
    result = score_record_relevance_hybrid(
        profile, tier1_text="", tier2_text="", tier3_text="antitussive",
        embedding_similarity=None,
    )
    assert result.fallback_mode is True


def test_fallback_mode_false_when_embedding_similarity_provided():
    profile = _profile_for("cough", ["cough treatment records"])
    result = score_record_relevance_hybrid(
        profile, tier1_text="cough", tier2_text="", tier3_text="",
        embedding_similarity=0.5,
    )
    assert result.fallback_mode is False


def test_fallback_mode_degrades_to_deterministic_engine_answer():
    """With embedding_similarity=None, the hybrid engine's answer for a
    corpus-derived match must equal the deterministic engine's own answer
    (same score, same match_type) -- true degradation, not a different
    weaker path."""
    from general_indication_relevance import score_record_relevance

    corpus = ["cough treatment with antitussive activity", "unrelated diabetes study"]
    profile = _profile_for("cough", corpus)
    deterministic = score_record_relevance(profile, "", "", "antitussive activity observed")
    hybrid = score_record_relevance_hybrid(
        profile, tier1_text="", tier2_text="", tier3_text="antitussive activity observed",
        embedding_similarity=None,
    )
    assert hybrid.match_type == deterministic.match_type
    assert hybrid.final_relevance_score == deterministic.score
