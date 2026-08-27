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

_EVIDENCE_UNRELATED = [
    {
        "evidence_id": "PMID1",
        "plant": "Valeriana officinalis",
        "text_snippet": "Valerian improved sleep latency in a randomized controlled trial.",
    },
]


def _dispatch(generation_reply=None, grounding_reply=None, grounding_side_effect=None):
    """Build a fake call_structured_json that answers the FIRST
    (generation, task='mechanistic_reasoning') call with generation_reply
    and every subsequent (verification, task='mechanistic_grounding_verification')
    call with grounding_reply -- or, if grounding_side_effect is given, a
    callable(kwargs) -> dict for per-call control over the grounding
    response (used when a test needs different verdicts for different
    edges/evidence)."""
    def _fake(**kwargs):
        if kwargs.get("task") == "mechanistic_reasoning":
            return generation_reply
        if grounding_side_effect is not None:
            return grounding_side_effect(kwargs)
        return grounding_reply
    return _fake


def _grounded(support_level, supported=True, supported_fields=None, unsupported_fields=None, reason=""):
    return {
        "supported": supported,
        "support_level": support_level,
        "supported_fields": supported_fields or [],
        "unsupported_fields": unsupported_fields or [],
        "reason": reason,
    }


# ---------------------------------------------------------------------
# G: direct mechanism edge, now also passing the semantic grounding layer
# ---------------------------------------------------------------------

def test_g_direct_mechanism_edge_stored_as_direct(monkeypatch):
    generation = {
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
    grounding = _grounded(svc.SUPPORT_DIRECT, supported_fields=["compound", "target_or_pathway"])

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, grounding))
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "direct"
    assert edges[0]["supporting_evidence_ids"] == ["PMID1"]
    assert edges[0]["grounding"]["support_level"] == svc.SUPPORT_DIRECT


# ---------------------------------------------------------------------
# H: inferred mechanism edge, now also passing semantic grounding for
# each link in the chain
# ---------------------------------------------------------------------

def test_h_inferred_mechanism_edge_stored_as_inferred(monkeypatch):
    generation = {
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
    grounding = _grounded(svc.SUPPORT_PARTIAL, supported_fields=["plant", "compound", "target_or_pathway"])

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, grounding))
    edges = svc.reason_about_mechanisms(_EVIDENCE_INFERRED_CHAIN)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "inferred"
    assert set(edges[0]["supporting_evidence_ids"]) == {"PMID1", "PMID2"}


def test_h_model_mislabels_chained_edge_as_direct_is_corrected_to_inferred(monkeypatch):
    """Even if the model itself mislabels a two-source chain as
    "direct", the enforced code-level rule downgrades it: a "direct"
    claim must trace to exactly one evidence item."""
    generation = {
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
    grounding = _grounded(svc.SUPPORT_PARTIAL, supported_fields=["plant", "compound", "target_or_pathway"])

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, grounding))
    edges = svc.reason_about_mechanisms(_EVIDENCE_INFERRED_CHAIN)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "inferred"


# ---------------------------------------------------------------------
# I: citation-existence-only edges are rejected (fabricated / missing ids)
# ---------------------------------------------------------------------

def test_i_unsupported_edge_with_fabricated_evidence_id_is_rejected(monkeypatch):
    generation = {
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
    # Grounding verifier should never even be reached for a fabricated
    # id -- layer 1 (citation existence) rejects it first.
    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, None))
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    assert edges == []


def test_i_edge_with_no_supporting_evidence_ids_is_rejected(monkeypatch):
    generation = {
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
    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, None))
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    assert edges == []


# ---------------------------------------------------------------------
# Semantic-grounding hardening tests 1-4 (Issue 1, required by the patch)
# ---------------------------------------------------------------------

def test_semantic_grounding_1_valid_citation_but_unrelated_text_is_rejected(monkeypatch):
    """A citation ID that genuinely exists in the input, but whose text
    does not support the claimed target/mechanism, must still be
    rejected -- this is the exact gap the hardening patch closes."""
    generation = {
        "edges": [{
            "plant": "Valeriana officinalis",
            "compound": "",
            "target_or_pathway": "serotonin receptor",
            "mechanism": "serotonin activation",
            "phenotype_or_endpoint": "mood improvement",
            "relationship_type": "direct",
            "supporting_evidence_ids": ["PMID1"],
            "confidence": 0.8,
            "rationale": "claimed serotonin link",
        }]
    }
    grounding = _grounded(
        svc.SUPPORT_INSUFFICIENT, supported=False,
        unsupported_fields=["target_or_pathway", "mechanism"],
        reason="Evidence discusses sleep latency, not serotonin receptors.",
    )
    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, grounding))
    edges = svc.reason_about_mechanisms(_EVIDENCE_UNRELATED)
    assert edges == []


def test_semantic_grounding_2_genuinely_supported_direct_edge_is_retained(monkeypatch):
    generation = {
        "edges": [{
            "plant": "Valeriana officinalis",
            "compound": "Valerenic acid",
            "target_or_pathway": "GABA-A receptor",
            "mechanism": "direct receptor binding",
            "phenotype_or_endpoint": "reduced neuronal excitability",
            "relationship_type": "direct",
            "supporting_evidence_ids": ["PMID1"],
            "confidence": 0.85,
            "rationale": "explicit binding statement",
        }]
    }
    grounding = _grounded(svc.SUPPORT_DIRECT, supported_fields=["compound", "target_or_pathway", "mechanism"])
    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, grounding))
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "direct"


def test_semantic_grounding_3_inferred_chain_with_both_links_supported_is_retained(monkeypatch):
    generation = {
        "edges": [{
            "plant": "Valeriana officinalis",
            "compound": "Valerenic acid",
            "target_or_pathway": "GABA-A receptor",
            "mechanism": "receptor modulation (chained)",
            "phenotype_or_endpoint": "possible sedative effect",
            "relationship_type": "inferred",
            "supporting_evidence_ids": ["PMID1", "PMID2"],
            "confidence": 0.5,
            "rationale": "plant->compound from PMID1, compound->target from PMID2",
        }]
    }
    grounding = _grounded(svc.SUPPORT_PARTIAL, supported_fields=["plant", "compound", "target_or_pathway"])
    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, grounding))
    edges = svc.reason_about_mechanisms(_EVIDENCE_INFERRED_CHAIN)
    assert len(edges) == 1
    assert edges[0]["relationship_type"] == "inferred"
    assert set(edges[0]["supporting_evidence_ids"]) == {"PMID1", "PMID2"}


def test_semantic_grounding_4_inferred_chain_with_one_unsupported_link_is_rejected(monkeypatch):
    """The chain claims compound -> target via PMID2, but PMID2 (in
    this scenario) does not actually mention the target -- the verifier
    must catch this and the edge must be rejected."""
    generation = {
        "edges": [{
            "plant": "Valeriana officinalis",
            "compound": "Valerenic acid",
            "target_or_pathway": "GABA-A receptor",
            "mechanism": "receptor modulation (chained)",
            "phenotype_or_endpoint": "possible sedative effect",
            "relationship_type": "inferred",
            "supporting_evidence_ids": ["PMID1", "PMID2"],
            "confidence": 0.5,
            "rationale": "claimed chain, but PMID2 does not actually support the target",
        }]
    }
    grounding = _grounded(
        svc.SUPPORT_INSUFFICIENT, supported=False,
        supported_fields=["plant", "compound"],
        unsupported_fields=["target_or_pathway"],
        reason="PMID2 does not mention GABA-A receptor.",
    )
    monkeypatch.setattr(svc.llm_client, "call_structured_json", _dispatch(generation, grounding))
    edges = svc.reason_about_mechanisms(_EVIDENCE_INFERRED_CHAIN)
    assert edges == []


def test_verification_unavailable_omits_the_edge_without_crashing(monkeypatch):
    """Part of the required architecture: verification unavailable ->
    omit unverifiable AI edge -> Stage 5 remains intact (fail closed for
    the edge, not the pipeline)."""
    generation = {
        "edges": [{
            "plant": "Valeriana officinalis",
            "compound": "Valerenic acid",
            "target_or_pathway": "GABA-A receptor",
            "mechanism": "direct receptor binding",
            "phenotype_or_endpoint": "reduced neuronal excitability",
            "relationship_type": "direct",
            "supporting_evidence_ids": ["PMID1"],
            "confidence": 0.85,
            "rationale": "x",
        }]
    }

    def _fake(**kwargs):
        if kwargs.get("task") == "mechanistic_reasoning":
            return generation
        raise RuntimeError("grounding verifier unavailable")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    edges = svc.reason_about_mechanisms(_EVIDENCE_DIRECT)
    # Must not raise, and the unverifiable edge is simply omitted.
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


def test_llm_failure_on_generation_returns_empty_list_never_raises(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)
    assert svc.reason_about_mechanisms(_EVIDENCE_DIRECT) == []
