import contextvars
import json

import ai_usage_telemetry as gov
import llm_client
import llm_extractor


def test_run_contexts_do_not_share_breaker_state():
    a = contextvars.Context()
    b = contextvars.Context()
    a.run(lambda: gov.start_new_ai_run("run-a"))
    b.run(lambda: gov.start_new_ai_run("run-b"))
    a.run(lambda: gov.get_ai_run_tracker().trip_breaker(gov.ERROR_INSUFFICIENT_QUOTA, "raw provider detail"))
    assert a.run(lambda: gov.get_ai_run_tracker().breaker_active()) is True
    assert b.run(lambda: gov.get_ai_run_tracker().breaker_active()) is False
    assert a.run(lambda: gov.get_ai_run_tracker().summary()["provider_circuit_reason"]) == gov.ERROR_INSUFFICIENT_QUOTA


def test_legacy_evidence_extractors_route_through_governed_client(monkeypatch):
    calls = []
    def fake(**kwargs):
        calls.append(kwargs["task"])
        if kwargs["task"] == "evidence_extraction":
            # Minimal schema-compatible shape expected by normalization helper.
            return {key: "" for key in llm_extractor.EVIDENCE_SCHEMA["properties"]}
        return {"safety_assertions": [], "regulatory_assertions": []}
    monkeypatch.setattr(llm_extractor.llm_client, "call_structured_json", fake)
    llm_extractor.extract_evidence_with_llm({"Source_Title": "x", "Notes": "x"})
    llm_extractor.extract_gate_assertions_with_llm({"Source_Title": "x", "Notes": "x"})
    assert calls == ["evidence_extraction", "semantic_gate_extraction"]


def test_malformed_json_is_tracked_and_not_cached(monkeypatch):
    class Response:
        output_text = "not-json"
        usage = None
    class Responses:
        def __init__(self): self.n = 0
        def create(self, **kwargs): self.n += 1; return Response()
    class Client:
        def __init__(self): self.responses = Responses()
    client = Client()
    monkeypatch.setattr(llm_client, "get_openai_client", lambda: client)
    llm_client.clear_cache()
    tracker = gov.start_new_ai_run("malformed")
    tracker.set_limit("x", 2)
    kwargs = dict(system_prompt="s", user_content="u", schema={"type":"object","properties":{},"additionalProperties":False}, schema_name="x", task="x")
    try:
        llm_client.call_structured_json(**kwargs)
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("malformed JSON should raise")
    summary = tracker.summary()
    assert summary["tasks"]["x"]["errors_by_category"][gov.ERROR_INVALID_OUTPUT] == 1
    assert summary["total_provider_attempts"] == 1
    # Not cached: a second call reaches provider again.
    try:
        llm_client.call_structured_json(**kwargs)
    except json.JSONDecodeError:
        pass
    assert client.responses.n == 2
