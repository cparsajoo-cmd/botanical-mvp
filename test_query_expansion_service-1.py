import query_expansion_service as svc


def test_combines_deterministic_and_ai_terms_deduplicated(monkeypatch):
    def _fake(**kwargs):
        return {"search_concepts": ["Insomnia", "sleep maintenance", "GABA-A modulation"]}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)

    result = svc.expand_query_terms(
        "Sleep and relaxation", deterministic_terms=["Sleep and relaxation", "insomnia"]
    )
    # deterministic terms come first, unchanged
    assert result[0] == "Sleep and relaxation"
    assert result[1] == "insomnia"
    # "Insomnia" (case-insensitive duplicate of "insomnia") must not be
    # added twice
    assert result.count("insomnia") + result.count("Insomnia") == 1
    assert "sleep maintenance" in result
    assert "GABA-A modulation" in result


def test_caps_total_combined_terms(monkeypatch):
    def _fake(**kwargs):
        return {"search_concepts": [f"concept {i}" for i in range(20)]}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)

    deterministic = [f"term {i}" for i in range(10)]
    result = svc.expand_query_terms("Inflammation", deterministic_terms=deterministic)
    assert len(result) <= svc.MAX_COMBINED_TERMS


def test_caps_ai_concepts_before_combining(monkeypatch):
    def _fake(**kwargs):
        return {"search_concepts": [f"concept {i}" for i in range(30)]}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)

    ai_concepts = svc.generate_ai_query_concepts("Inflammation")
    assert len(ai_concepts) <= svc.MAX_AI_CONCEPTS


def test_ai_failure_falls_back_to_deterministic_terms_only(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)

    deterministic = ["Sleep and relaxation", "insomnia", "sleep disorder"]
    result = svc.expand_query_terms("Sleep and relaxation", deterministic_terms=deterministic)
    assert result == deterministic


def test_no_indication_returns_empty_ai_concepts_without_calling_llm(monkeypatch):
    called = {"n": 0}

    def _fake(**kwargs):
        called["n"] += 1
        return {"search_concepts": ["x"]}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)

    assert svc.generate_ai_query_concepts("") == []
    assert called["n"] == 0


def test_malformed_ai_output_is_ignored(monkeypatch):
    def _fake(**kwargs):
        return {"search_concepts": "not a list"}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)

    assert svc.generate_ai_query_concepts("Sleep") == []


def test_rejects_overlong_concepts(monkeypatch):
    def _fake(**kwargs):
        return {"search_concepts": ["ok concept", "x" * 200]}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)

    result = svc.generate_ai_query_concepts("Sleep")
    assert result == ["ok concept"]
