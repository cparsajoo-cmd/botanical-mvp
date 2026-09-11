"""Regression tombstone for the retired PubMed token-relation heuristic.

The legacy ``verify_pubmed_intervention_attribution`` API was intentionally
removed when Problem 1 moved to the canonical Candidate_Intervention_Assertion
architecture.  This file keeps the historical test filename so web/GitHub
upload workflows that cannot delete files can overwrite the obsolete suite
instead of accidentally forcing the removed heuristic back into production.

These tests protect the architectural boundary that replaced it:
- the legacy heuristic must stay absent;
- a source-grounded candidate-containing assertion may verify;
- a verbatim but candidate-unrelated supporting span must fail closed.
"""

import candidate_attribution as ca
from candidate_intervention_assertion import assertion_from_llm_extraction


def _payload(span: str, *, confidence: float = 0.95) -> dict:
    return {
        "candidate_intervention_role": "studied_intervention",
        "candidate_intervention_polarity": "positive",
        "candidate_intervention_temporality": "current_study",
        "candidate_intervention_supporting_text": span,
        "candidate_intervention_confidence": confidence,
    }


def test_legacy_pubmed_token_heuristic_remains_retired():
    """Do not reintroduce the brittle sentence/token heuristic for CI compatibility."""
    assert not hasattr(ca, "verify_pubmed_intervention_attribution")


def test_canonical_assertion_accepts_grounded_candidate_span():
    span = "Participants received Ficticus alpinum extract daily."
    source = f"Background text. {span} Follow-up was eight weeks."

    assertion = assertion_from_llm_extraction(
        _payload(span),
        source_text=source,
        scientific_name="Ficticus alpinum",
    )

    assert assertion.verified is True


def test_canonical_assertion_rejects_unrelated_verbatim_span():
    span = "Participants received placebo."
    source = f"{span} Ficticus alpinum was mentioned only in the background."

    assertion = assertion_from_llm_extraction(
        _payload(span),
        source_text=source,
        scientific_name="Ficticus alpinum",
    )

    assert assertion.verified is False
