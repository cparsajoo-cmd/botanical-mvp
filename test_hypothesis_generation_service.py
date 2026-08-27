import hypothesis_generation_service as svc

_EDGES = [{
    "plant": "Valeriana officinalis", "compound": "Valerenic acid",
    "target_or_pathway": "GABA-A receptor", "mechanism": "receptor modulation",
    "phenotype_or_endpoint": "reduced excitability", "relationship_type": "inferred",
    "supporting_evidence_ids": ["PMID1", "PMID2"], "confidence": 0.5,
}]
_SYNTHESIS = {
    "overall_consistency": "mixed", "heterogeneity_reason": "unresolved",
    "summary": "mixed clinical evidence", "contradictions": [],
}


def test_hypotheses_are_always_labeled_rd_hypothesis(monkeypatch):
    def _fake(**kwargs):
        return {
            "hypotheses": [{
                "hypothesis": "Strong mechanistic rationale but limited clinical evidence "
                               "suggests a dose-ranging clinical trial could be valuable.",
                "hypothesis_type": "evidence_gap",
                "supporting_evidence_ids": ["PMID1"],
                "contradicting_evidence_ids": [],
                "uncertainties": ["No dose-response clinical data available"],
                "confidence": 0.6,
                "research_next_step": "Run a dose-ranging RCT in adults with insomnia.",
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.generate_hypotheses(_EDGES, _SYNTHESIS)
    assert len(result) == 1
    assert result[0]["evidence_label"] == "rd_hypothesis"
    assert result[0]["hypothesis_type"] == "evidence_gap"
    assert result[0]["supporting_evidence_ids"] == ["PMID1"]


def test_evidence_label_cannot_be_overridden_by_model_output(monkeypatch):
    """Even if the model output somehow included an evidence_label
    field, the schema doesn't define one for the model to set, and this
    module assigns it itself -- confirm the fixed constant always wins."""
    def _fake(**kwargs):
        return {
            "hypotheses": [{
                "hypothesis": "test", "hypothesis_type": "other",
                "supporting_evidence_ids": [], "contradicting_evidence_ids": [],
                "uncertainties": [], "confidence": 0.3,
                "research_next_step": "next step",
                "evidence_label": "established_evidence",  # model cannot inject this
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.generate_hypotheses(_EDGES, _SYNTHESIS)
    assert result[0]["evidence_label"] == "rd_hypothesis"


def test_fabricated_supporting_evidence_id_is_dropped(monkeypatch):
    def _fake(**kwargs):
        return {
            "hypotheses": [{
                "hypothesis": "test", "hypothesis_type": "other",
                "supporting_evidence_ids": ["PMID1", "FABRICATED"],
                "contradicting_evidence_ids": [],
                "uncertainties": [], "confidence": 0.3, "research_next_step": "x",
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.generate_hypotheses(_EDGES, _SYNTHESIS)
    assert result[0]["supporting_evidence_ids"] == ["PMID1"]


def test_no_mechanism_or_synthesis_returns_empty_without_calling_llm(monkeypatch):
    called = {"n": 0}

    def _fake(**kwargs):
        called["n"] += 1
        return {"hypotheses": []}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    assert svc.generate_hypotheses([], None) == []
    assert called["n"] == 0


def test_llm_failure_returns_empty_list_never_raises(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)
    assert svc.generate_hypotheses(_EDGES, _SYNTHESIS) == []


def test_output_never_contains_a_numeric_score_field():
    """Structural guarantee: the schema itself has no field that could
    be mistaken for or used as a final candidate score."""
    assert "score" not in svc.HYPOTHESIS_SCHEMA["properties"]["hypotheses"]["items"]["properties"]
