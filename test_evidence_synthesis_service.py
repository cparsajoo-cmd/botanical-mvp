import evidence_synthesis_service as svc


_MIXED_EVIDENCE = [
    {"evidence_id": "A", "plant": "X", "result_direction": "positive", "study_model": "human",
     "text_snippet": "Standardized extract improved symptoms in a randomized trial."},
    {"evidence_id": "B", "plant": "X", "result_direction": "no_effect", "study_model": "human",
     "text_snippet": "No significant effect vs placebo in a different randomized trial."},
    {"evidence_id": "C", "plant": "X", "result_direction": "positive", "study_model": "animal",
     "text_snippet": "Positive effect observed in a rodent model."},
]


def test_j_mixed_evidence_and_heterogeneity_captured(monkeypatch):
    def _fake(**kwargs):
        return {
            "overall_consistency": "mixed",
            "clinical_vs_preclinical_disagreement": False,
            "heterogeneity_reason": "unresolved",
            "heterogeneity_explanation": "Studies A and B disagree with no clear explanatory field.",
            "contradictions": [
                {"evidence_id_a": "A", "evidence_id_b": "B", "description": "positive vs no effect"},
            ],
            "summary": "Evidence is mixed among human studies; preclinical evidence is positive.",
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.synthesize_evidence(_MIXED_EVIDENCE)
    assert result is not None
    assert result["overall_consistency"] == "mixed"
    assert result["heterogeneity_reason"] == "unresolved"
    assert len(result["contradictions"]) == 1
    assert result["contradictions"][0]["evidence_id_a"] == "A"
    assert result["evidence_items_considered"] == 3


def test_j_no_false_consensus_when_model_tries_to_claim_consistency(monkeypatch):
    """Even a model output has to pass through the fixed enum -- an
    invalid/garbage consistency value is rejected outright rather than
    silently accepted as a false consensus."""
    def _fake(**kwargs):
        return {
            "overall_consistency": "definitely works",  # not a legal enum value
            "clinical_vs_preclinical_disagreement": False,
            "heterogeneity_reason": "unresolved",
            "heterogeneity_explanation": "",
            "contradictions": [],
            "summary": "",
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.synthesize_evidence(_MIXED_EVIDENCE)
    assert result is None


def test_contradiction_with_fabricated_evidence_id_is_dropped(monkeypatch):
    def _fake(**kwargs):
        return {
            "overall_consistency": "mixed",
            "clinical_vs_preclinical_disagreement": False,
            "heterogeneity_reason": "unresolved",
            "heterogeneity_explanation": "",
            "contradictions": [
                {"evidence_id_a": "A", "evidence_id_b": "DOES_NOT_EXIST", "description": "fabricated"},
                {"evidence_id_a": "A", "evidence_id_b": "B", "description": "real"},
            ],
            "summary": "",
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.synthesize_evidence(_MIXED_EVIDENCE)
    assert len(result["contradictions"]) == 1
    assert result["contradictions"][0]["description"] == "real"


def test_raw_evidence_items_are_never_mutated(monkeypatch):
    def _fake(**kwargs):
        return {
            "overall_consistency": "mixed", "clinical_vs_preclinical_disagreement": False,
            "heterogeneity_reason": "unresolved", "heterogeneity_explanation": "",
            "contradictions": [], "summary": "",
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    original = [dict(item) for item in _MIXED_EVIDENCE]
    svc.synthesize_evidence(_MIXED_EVIDENCE)
    assert _MIXED_EVIDENCE == original


def test_no_evidence_returns_none_without_calling_llm(monkeypatch):
    called = {"n": 0}

    def _fake(**kwargs):
        called["n"] += 1
        return {}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    assert svc.synthesize_evidence([]) is None
    assert called["n"] == 0


def test_llm_failure_returns_none_never_raises(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("timeout")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)
    assert svc.synthesize_evidence(_MIXED_EVIDENCE) is None
