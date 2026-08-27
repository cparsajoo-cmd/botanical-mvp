"""Tests A and B from the hybrid AI-R&D architecture acceptance criteria:
A) a valid structured LLM intent result is normalized correctly;
B) a malformed/failing LLM response falls back to the existing
   deterministic parser and never breaks the caller.

No live OpenAI call is made anywhere in this file -- llm_client.call_structured_json
is monkeypatched directly.
"""
import free_text_question_parser as detparser
import scientific_intent_service as svc


def test_a_valid_structured_intent_is_normalized(monkeypatch):
    captured = {}

    def _fake_call_structured_json(**kwargs):
        captured.update(kwargs)
        return {
            "primary_indication": "sleep maintenance insomnia",
            "therapeutic_domain": "sleep",
            "population": ["older adults", "elderly"],
            "desired_outcomes": ["reduce nocturnal awakenings"],
            "undesired_effects": ["next-day sedation", "non-sedating"],
            "route": "oral product",
            "candidate_type": "botanical",
            "relevant_mechanisms": ["GABAergic signalling", "circadian regulation"],
            "search_concepts": ["insomnia", "sleep maintenance", "GABA-A"],
            "confidence": 0.87,
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake_call_structured_json)

    result = svc.parse_scientific_intent(
        "Find oral botanical candidates that may help older adults with "
        "repeated nocturnal awakenings without causing strong next-day sedation."
    )

    assert result.ai_used is True
    assert result.ai_fallback_reason == ""
    assert result.indication == "Sleep and relaxation"
    assert result.route == "Oral"
    assert "Elderly / older adults" in result.target_population
    assert "Non-sedating / low sedation" in result.safety_constraints
    assert result.confidence == 0.87
    assert "GABAergic signalling" in result.relevant_mechanisms
    assert "insomnia" in result.search_concepts
    assert result.structured_intent["primary_indication"] == "sleep maintenance insomnia"
    # The intent parser must remain indication-agnostic: it uses the
    # project's shared task/model/schema-version conventions, not a
    # hardcoded model name.
    assert captured["task"] == "scientific_intent"
    assert captured["model_env_var"] == svc.INTENT_MODEL_ENV_VAR


def test_a_works_across_multiple_therapeutic_domains(monkeypatch):
    """The parser must not be specialized to sleep -- verify a second,
    unrelated domain normalizes correctly through the same code path."""
    def _fake_call_structured_json(**kwargs):
        return {
            "primary_indication": "joint inflammation",
            "therapeutic_domain": "inflammation",
            "population": ["adults"],
            "desired_outcomes": ["reduce joint pain"],
            "undesired_effects": [],
            "route": "topical",
            "candidate_type": "botanical",
            "relevant_mechanisms": ["COX-2 inhibition"],
            "search_concepts": ["osteoarthritis", "anti-inflammatory"],
            "confidence": 0.7,
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake_call_structured_json)

    result = svc.parse_scientific_intent(
        "I need a topical botanical for joint inflammation in adults."
    )
    assert result.ai_used is True
    assert result.indication == "Inflammation"
    assert result.route == "Topical"


def test_b_malformed_json_falls_back_to_deterministic_parser(monkeypatch):
    def _raise(**kwargs):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)

    text = "a botanical oral product for mild cognitive impairment in the elderly, EU market"
    result = svc.parse_scientific_intent(text)
    expected = detparser.parse_free_text_question(text)

    assert result.ai_used is False
    assert "ValueError" in result.ai_fallback_reason
    assert result.indication == expected.indication
    assert result.dosage_form == expected.dosage_form
    assert result.market == expected.market
    assert result.target_population == expected.target_population


def test_b_llm_unavailable_missing_api_key_falls_back(monkeypatch):
    def _raise(**kwargs):
        raise ValueError("OPENAI_API_KEY is missing.")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _raise)

    text = "sleep support capsule for the EU market"
    result = svc.parse_scientific_intent(text)
    expected = detparser.parse_free_text_question(text)

    assert result.ai_used is False
    assert result.indication == expected.indication
    assert result.dosage_form == expected.dosage_form
    assert result.market == expected.market


def test_b_schema_valid_but_semantically_empty_falls_back(monkeypatch):
    """A well-formed but unusable AI result (nothing recognizable after
    normalization) must not silently produce an empty AIParsedQuestion --
    it must fall back to the deterministic parser so the pipeline still
    gets whatever the keyword parser can recognize."""
    def _fake_call_structured_json(**kwargs):
        return {
            "primary_indication": "xyzzy nonsense",
            "therapeutic_domain": "unknown",
            "population": [],
            "desired_outcomes": [],
            "undesired_effects": [],
            "route": "",
            "candidate_type": "",
            "relevant_mechanisms": [],
            "search_concepts": [],
            "confidence": 0.1,
        }

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake_call_structured_json)

    text = "please help me think through my research project this quarter"
    result = svc.parse_scientific_intent(text)
    expected = detparser.parse_free_text_question(text)

    assert result.ai_used is False
    assert "nothing usable" in result.ai_fallback_reason
    assert result.indication == expected.indication is None
    assert result.market == expected.market is None


def test_empty_text_returns_empty_fallback_without_calling_llm(monkeypatch):
    called = {"n": 0}

    def _fake_call_structured_json(**kwargs):
        called["n"] += 1
        raise AssertionError("should not be called for empty input")

    monkeypatch.setattr(svc.llm_client, "call_structured_json", _fake_call_structured_json)

    result = svc.parse_scientific_intent("")
    assert result.ai_used is False
    assert result.ai_fallback_reason == "empty_input"
    assert called["n"] == 0
