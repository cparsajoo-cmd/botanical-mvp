import ai_botanical_entity_extractor as svc


def test_accepts_common_name_proposal_above_confidence_threshold(monkeypatch):
    def _fake(**kwargs):
        return {
            "entities": [
                {
                    "original_mention": "lemon balm",
                    "proposed_scientific_name": "Melissa officinalis",
                    "common_name": "lemon balm",
                    "genus": "Melissa",
                    "species": "officinalis",
                    "is_botanical": True,
                    "confidence": 0.9,
                    "context_support": "lemon balm extract reduced anxiety scores",
                }
            ]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)

    result = svc.extract_botanical_entities_ai(
        "Effects of lemon balm on anxiety", "lemon balm extract reduced anxiety scores in a small trial"
    )
    assert len(result) == 1
    assert result[0]["proposed_scientific_name"] == "Melissa officinalis"
    assert svc.candidate_strings_for_validation(result) == ["Melissa officinalis"]


def test_rejects_low_confidence_proposal(monkeypatch):
    def _fake(**kwargs):
        return {
            "entities": [
                {
                    "original_mention": "some plant",
                    "proposed_scientific_name": "",
                    "common_name": "",
                    "genus": "",
                    "species": "",
                    "is_botanical": True,
                    "confidence": 0.1,
                    "context_support": "",
                }
            ]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.extract_botanical_entities_ai("title", "abstract")
    assert result == []


def test_rejects_non_botanical_flagged_entity(monkeypatch):
    """False-positive protection: even a high-confidence entity is
    dropped by this pre-filter if the model itself flagged is_botanical
    false (e.g. a drug/compound/gene the model correctly did not treat
    as a plant)."""
    def _fake(**kwargs):
        return {
            "entities": [
                {
                    "original_mention": "ibuprofen",
                    "proposed_scientific_name": "",
                    "common_name": "",
                    "genus": "",
                    "species": "",
                    "is_botanical": False,
                    "confidence": 0.95,
                    "context_support": "ibuprofen was used as an active comparator",
                }
            ]
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    result = svc.extract_botanical_entities_ai("title", "abstract mentioning ibuprofen")
    assert result == []


def test_empty_entities_list_is_fine(monkeypatch):
    monkeypatch.setattr(svc.llm_client, "call_structured_json", lambda **kw: {"entities": []})
    assert svc.extract_botanical_entities_ai("title", "abstract") == []


def test_llm_unavailable_returns_empty_list_never_raises(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("OPENAI_API_KEY is missing.")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)
    result = svc.extract_botanical_entities_ai("title", "abstract")
    assert result == []


def test_malformed_json_shape_returns_empty_list(monkeypatch):
    monkeypatch.setattr(svc.llm_client, "call_structured_json", lambda **kw: {"entities": "not a list"})
    assert svc.extract_botanical_entities_ai("title", "abstract") == []


def test_no_title_or_abstract_returns_empty_without_calling_llm(monkeypatch):
    called = {"n": 0}

    def _fake(**kwargs):
        called["n"] += 1
        return {"entities": []}

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake)
    assert svc.extract_botanical_entities_ai("", "") == []
    assert called["n"] == 0


def test_candidate_strings_dedup_case_insensitive():
    entities = [
        {"proposed_scientific_name": "Melissa officinalis", "original_mention": "lemon balm"},
        {"proposed_scientific_name": "melissa officinalis", "original_mention": "Lemon Balm"},
        {"proposed_scientific_name": "", "original_mention": "Withania somnifera"},
    ]
    result = svc.candidate_strings_for_validation(entities)
    assert result == ["Melissa officinalis", "Withania somnifera"]
