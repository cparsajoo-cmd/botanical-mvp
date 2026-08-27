import mechanistic_reasoning_service as svc


_EVIDENCE_DIRECT = [
    {
        "evidence_id": "PMID1",
        "plant": "Valeriana officinalis",
        "compound": "Valerenic acid",
        "target": "GABA-A receptor",
        "mechanism_text": "Valerenic acid directly binds and modulates the GABA-A receptor.",
        "result_direction": "positive",
        "study_model": "in_vitro",
        "text_snippet": "Valerenic acid was shown to bind and positively modulate GABA-A receptors.",
    },
]

_EVIDENCE_INFERRED_CHAIN = [
    {
        "evidence_id": "PMID1",
        "plant": "Valeriana officinalis",
        "compound": "Valerenic acid",
        "text_snippet": "Valeriana officinalis extract contains valerenic acid.",
    },
    {
        "evidence_id": "PMID2",
        "compound": "Valerenic acid",
        "target": "GABA-A receptor",
        "text_snippet": "Independent pharmacology study: valerenic acid modulates GABA-A receptors.",
    },
]


def test_g_direct_mechanism_edge_stored_as_direct(monkeypatch):
    def _fake(**kwargs):
        return {
            "edges": [{
                "plant": "Valeriana officinalis",
                "compound": "Valerenic acid",
                "target_or_pathway": "GABA-A receptor",
                "mechanism": "direct receptor binding",
                "phenotype_or_endpoint": "reduced neuronal excitability",
                "relationship_type": "direct",
                "supporting_evidence_ids": ["PMID1"],
                "confidence": 0.85,
                "rationale": "Same source states the direct binding.",
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "direct"
    assert edges[0]["supporting_evidence_ids"] == ["PMID1"]


def test_h_inferred_mechanism_edge_stored_as_inferred(monkeypatch):
    def _fake(**kwargs):
        return {
            "edges": [{
                "plant": "Valeriana officinalis",
                "compound": "Valerenic acid",
                "target_or_pathway": "GABA-A receptor",
                "mechanism": "receptor modulation (chained)",
                "phenotype_or_endpoint": "possible sedative effect",
                "relationship_type": "inferred",
                "supporting_evidence_ids": ["PMID1", "PMID2"],
                "confidence": 0.5,
                "rationale": "Plant->compound from PMID1, compound->target from PMID2.",
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    edges = svc.reason_about_mechanisms(_EVIDENCE_INFERRED_CHAIN)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "inferred"
    assert set(edges[0]["supporting_evidence_ids"]) == {"PMID1", "PMID2"}


def test_h_model_mislabels_chained_edge_as_direct_is_corrected_to_inferred(monkeypatch):
    """Even if the model itself mislabels a two-source chain as
    "direct", the enforced code-level rule downgrades it: a "direct"
    claim must trace to exactly one evidence item."""
    def _fake(**kwargs):
        return {
            "edges": [{
                "plant": "Valeriana officinalis",
                "compound": "Valerenic acid",
                "target_or_pathway": "GABA-A receptor",
                "mechanism": "receptor modulation",
                "phenotype_or_endpoint": "sedative effect",
                "relationship_type": "direct",
                "supporting_evidence_ids": ["PMID1", "PMID2"],
                "confidence": 0.6,
                "rationale": "mislabeled by model",
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    edges = svc.reason_about_mechanisms(_EVIDENCE_INFERRED_CHAIN)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "inferred"


def test_i_unsupported_edge_with_fabricated_evidence_id_is_rejected(monkeypatch):
    def _fake(**kwargs):
        return {
            "edges": [{
                "plant": "Valeriana officinalis",
                "compound": "Valerenic acid",
                "target_or_pathway": "Serotonin receptor",
                "mechanism": "fabricated link",
                "phenotype_or_endpoint": "mood improvement",
                "relationship_type": "direct",
                "supporting_evidence_ids": ["PMID_DOES_NOT_EXIST"],
                "confidence": 0.9,
                "rationale": "hallucinated",
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    assert edges == []


def test_i_edge_with_no_supporting_evidence_ids_is_rejected(monkeypatch):
    def _fake(**kwargs):
        return {
            "edges": [{
                "plant": "Valeriana officinalis",
                "compound": "Valerenic acid",
                "target_or_pathway": "GABA-A receptor",
                "mechanism": "unsupported",
                "phenotype_or_endpoint": "unknown",
                "relationship_type": "direct",
                "supporting_evidence_ids": [],
                "confidence": 0.9,
                "rationale": "no citation",
            }]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    assert edges == []


def test_no_evidence_items_returns_empty_without_calling_llm(monkeypatch):
    called = {"n": 0}

    def _fake(**kwargs):
        called["n"] += 1
        return {"edges": []}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    assert svc.reason_about_mechanisms([]) == []
    assert svc.reason_about_mechanisms([{"plant": "x"}]) == []  # missing evidence_id
    assert called["n"] == 0


def test_llm_failure_returns_empty_list_never_raises(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)
    assert svc.reason_about_mechanisms(_EVIDENCE_DIRECT) == []
