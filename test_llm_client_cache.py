"""Issue 3 hardening tests: llm_client.call_structured_json's cache key
must include a stable hash of system_prompt and of the JSON schema, not
just task/model/schema_version/user_content -- so a changed prompt or
schema is never served a stale cached result even if schema_version was
not bumped.
"""
import llm_client


_SCHEMA_A = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
_SCHEMA_B = {"type": "object", "properties": {"y": {"type": "string"}}, "required": ["y"]}


class _FakeResponse:
    def __init__(self, text):
        self.output_text = text


def _install_fake_client(monkeypatch, call_log, reply_text='{"x": "ok"}'):
    class _FakeResponses:
        def create(self, **kwargs):
            call_log.append(kwargs)
            return _FakeResponse(reply_text)

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setattr(llm_client, "get_openai_client", lambda: _FakeClient())


def setup_function(_):
    llm_client.clear_cache()


def test_cache1_different_system_prompt_produces_different_cache_key(monkeypatch):
    calls = []
    _install_fake_client(monkeypatch, calls)

    llm_client.call_structured_json(
        system_prompt="Prompt version A", user_content="same input",
        schema=_SCHEMA_A, schema_name="s", task="t", schema_version="v1",
    )
    llm_client.call_structured_json(
        system_prompt="Prompt version B", user_content="same input",
        schema=_SCHEMA_A, schema_name="s", task="t", schema_version="v1",
    )
    # Two distinct API calls -- no stale cache hit across the prompt change.
    assert len(calls) == 2


def test_cache2_different_schema_produces_different_cache_key(monkeypatch):
    calls = []
    _install_fake_client(monkeypatch, calls, reply_text='{"x": "ok", "y": "ok"}')

    llm_client.call_structured_json(
        system_prompt="same prompt", user_content="same input",
        schema=_SCHEMA_A, schema_name="s", task="t", schema_version="v1",
    )
    llm_client.call_structured_json(
        system_prompt="same prompt", user_content="same input",
        schema=_SCHEMA_B, schema_name="s", task="t", schema_version="v1",
    )
    assert len(calls) == 2


def test_cache_regression_identical_everything_is_a_cache_hit(monkeypatch):
    calls = []
    _install_fake_client(monkeypatch, calls)

    kwargs = dict(
        system_prompt="same prompt", user_content="same input",
        schema=_SCHEMA_A, schema_name="s", task="t", schema_version="v1",
    )
    result_1 = llm_client.call_structured_json(**kwargs)
    result_2 = llm_client.call_structured_json(**kwargs)

    assert len(calls) == 1  # only one real API call
    assert result_1 == result_2 == {"x": "ok"}


def test_schema_key_order_does_not_matter_for_cache_hit(monkeypatch):
    """Stable serialization (sorted keys) means two schemas that differ
    only in key order still hit the cache -- they are semantically
    identical."""
    calls = []
    _install_fake_client(monkeypatch, calls)

    schema_a = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    schema_a_reordered = {"required": ["x"], "properties": {"x": {"type": "string"}}, "type": "object"}

    llm_client.call_structured_json(
        system_prompt="p", user_content="i", schema=schema_a,
        schema_name="s", task="t", schema_version="v1",
    )
    llm_client.call_structured_json(
        system_prompt="p", user_content="i", schema=schema_a_reordered,
        schema_name="s", task="t", schema_version="v1",
    )
    assert len(calls) == 1


def test_exceptions_are_never_cached(monkeypatch):
    calls = {"n": 0}

    class _FailingResponses:
        def create(self, **kwargs):
            calls["n"] += 1
            raise RuntimeError("transient network error")

    class _FailingClient:
        responses = _FailingResponses()

    monkeypatch.setattr(llm_client, "get_openai_client", lambda: _FailingClient())

    for _ in range(2):
        try:
            llm_client.call_structured_json(
                system_prompt="p", user_content="i", schema=_SCHEMA_A,
                schema_name="s", task="t", schema_version="v1",
            )
        except RuntimeError:
            pass
    # Both calls actually hit the (failing) API -- no error was cached.
    assert calls["n"] == 2
