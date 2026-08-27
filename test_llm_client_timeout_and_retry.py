"""Part F4 -- llm_client.call_structured_json must never let one slow or
transiently-failing OpenAI request block a caller indefinitely: every
request gets an explicit timeout, and only TRANSIENT failures (timeout /
rate-limit / connection / server error) get one small, bounded retry
before the exception is finally raised for the caller's own fail-open
handling.
"""
import pytest

import llm_client


_SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


class _FakeResponse:
    def __init__(self, text):
        self.output_text = text


class _TimeoutError(Exception):
    pass


class _AuthError(Exception):
    pass


def setup_function(_):
    llm_client.clear_cache()


def _install_fake_client(monkeypatch, create_fn):
    class _FakeResponses:
        def create(self, **kwargs):
            return create_fn(**kwargs)

    class _FakeClient:
        responses = _FakeResponses()

    monkeypatch.setattr(llm_client, "get_openai_client", lambda: _FakeClient())


def test_every_request_carries_an_explicit_timeout(monkeypatch):
    monkeypatch.delenv(llm_client.DEFAULT_TIMEOUT_ENV_VAR, raising=False)
    seen_kwargs = []

    def _create(**kwargs):
        seen_kwargs.append(kwargs)
        return _FakeResponse('{"x": "ok"}')

    _install_fake_client(monkeypatch, _create)
    llm_client.call_structured_json(
        system_prompt="p", user_content="u", schema=_SCHEMA,
        schema_name="s", task="t", use_cache=False,
    )
    assert seen_kwargs[0]["timeout"] == llm_client.DEFAULT_TIMEOUT_SECONDS_FALLBACK


def test_timeout_env_var_overrides_default(monkeypatch):
    monkeypatch.setenv(llm_client.DEFAULT_TIMEOUT_ENV_VAR, "5")
    seen_kwargs = []

    def _create(**kwargs):
        seen_kwargs.append(kwargs)
        return _FakeResponse('{"x": "ok"}')

    _install_fake_client(monkeypatch, _create)
    llm_client.call_structured_json(
        system_prompt="p", user_content="u", schema=_SCHEMA,
        schema_name="s", task="t", use_cache=False,
    )
    assert seen_kwargs[0]["timeout"] == 5.0


def test_transient_failure_is_retried_up_to_bounded_limit_then_raises(monkeypatch):
    monkeypatch.setenv(llm_client.DEFAULT_MAX_RETRIES_ENV_VAR, "1")
    call_count = {"n": 0}

    def _create(**kwargs):
        call_count["n"] += 1
        raise _TimeoutError("Request timed out")

    _install_fake_client(monkeypatch, _create)
    with pytest.raises(_TimeoutError):
        llm_client.call_structured_json(
            system_prompt="p", user_content="u", schema=_SCHEMA,
            schema_name="s", task="t", use_cache=False,
        )
    # max_retries=1 -> at most 2 attempts total, never unbounded.
    assert call_count["n"] == 2


def test_transient_failure_succeeds_on_retry(monkeypatch):
    monkeypatch.setenv(llm_client.DEFAULT_MAX_RETRIES_ENV_VAR, "1")
    call_count = {"n": 0}

    def _create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _TimeoutError("Request timed out")
        return _FakeResponse('{"x": "ok"}')

    _install_fake_client(monkeypatch, _create)
    result = llm_client.call_structured_json(
        system_prompt="p", user_content="u", schema=_SCHEMA,
        schema_name="s", task="t", use_cache=False,
    )
    assert result == {"x": "ok"}
    assert call_count["n"] == 2


def test_non_transient_failure_is_never_retried(monkeypatch):
    monkeypatch.setenv(llm_client.DEFAULT_MAX_RETRIES_ENV_VAR, "3")
    call_count = {"n": 0}

    def _create(**kwargs):
        call_count["n"] += 1
        raise _AuthError("invalid_api_key: Incorrect API key provided")

    _install_fake_client(monkeypatch, _create)
    with pytest.raises(_AuthError):
        llm_client.call_structured_json(
            system_prompt="p", user_content="u", schema=_SCHEMA,
            schema_name="s", task="t", use_cache=False,
        )
    # Non-transient (auth) error -- zero retries, even with max_retries=3.
    assert call_count["n"] == 1


# ---------------------------------------------------------------------
# Part 17 (Stage 2 remediation) -- deadline_seconds caps the per-attempt
# timeout and the retry budget to the caller's own remaining time.
# ---------------------------------------------------------------------
def test_deadline_seconds_caps_the_per_attempt_timeout(monkeypatch):
    monkeypatch.delenv(llm_client.DEFAULT_TIMEOUT_ENV_VAR, raising=False)
    seen_kwargs = []

    def _create(**kwargs):
        seen_kwargs.append(kwargs)
        return _FakeResponse('{"x": "ok"}')

    _install_fake_client(monkeypatch, _create)
    llm_client.call_structured_json(
        system_prompt="p", user_content="u", schema=_SCHEMA,
        schema_name="s", task="t", use_cache=False, deadline_seconds=7,
    )
    # Configured default (20s) is larger than the 7s remaining budget --
    # the smaller of the two must be used.
    assert seen_kwargs[0]["timeout"] <= 7


def test_deadline_seconds_does_not_shrink_timeout_when_budget_is_larger(monkeypatch):
    monkeypatch.setenv(llm_client.DEFAULT_TIMEOUT_ENV_VAR, "5")
    seen_kwargs = []

    def _create(**kwargs):
        seen_kwargs.append(kwargs)
        return _FakeResponse('{"x": "ok"}')

    _install_fake_client(monkeypatch, _create)
    llm_client.call_structured_json(
        system_prompt="p", user_content="u", schema=_SCHEMA,
        schema_name="s", task="t", use_cache=False, deadline_seconds=60,
    )
    assert seen_kwargs[0]["timeout"] == 5.0


def test_retry_is_not_attempted_once_deadline_already_exhausted(monkeypatch):
    monkeypatch.setenv(llm_client.DEFAULT_MAX_RETRIES_ENV_VAR, "3")
    call_count = {"n": 0}

    def _create(**kwargs):
        call_count["n"] += 1
        raise _TimeoutError("Request timed out")

    _install_fake_client(monkeypatch, _create)
    with pytest.raises(TimeoutError):
        llm_client.call_structured_json(
            system_prompt="p", user_content="u", schema=_SCHEMA,
            schema_name="s", task="t", use_cache=False,
            # A deadline already in the past: the very first attempt must
            # be treated as already-exhausted, and no retry attempted.
            deadline_seconds=-1,
        )
    assert call_count["n"] == 0
