"""Centralized OpenAI access for this project.

WHY THIS MODULE EXISTS
Before this module, llm_extractor.py owned the only real
get_openai_client() implementation, and embedding_service.py lazily
imported that same function rather than defining a second one (so the
two were already NOT duplicated in practice -- see embedding_service.py's
own get_openai_client() docstring). What was genuinely missing was a
single place for the pieces every new AI service (scientific intent,
query expansion, botanical entity extraction, mechanistic reasoning,
evidence synthesis, hypothesis generation) would otherwise have to
reimplement: model selection with a per-task override convention (the
existing OPENAI_GATE_MODEL pattern, generalized), the "retry once
against the project default model on a model-name error" fallback,
structured (strict json_schema) Responses API calls, and a small
result cache. This module is that single place.

BACKWARD COMPATIBILITY
llm_extractor.py's own get_openai_client name is preserved (re-exported
from here) because at least one existing test
(test_llm_extractor_gate_assertion_prompt.py) monkeypatches
``llm_extractor.get_openai_client`` directly by attribute assignment.
Re-exporting keeps that pattern working unchanged -- see llm_extractor.py.

FAIL-OPEN IS THE CALLER'S RESPONSIBILITY
Nothing in this module swallows exceptions. call_structured_json() raises
on any non-model-name error (auth, rate limit, schema/prompt errors,
malformed JSON) exactly like the pattern extract_gate_assertions_with_llm
already used. Every new AI service built on top of this module is
responsible for catching those exceptions and falling back to its
deterministic counterpart -- this module only makes the underlying call
easy to get right and consistent; it does not decide pipeline behavior
and never touches Streamlit session state.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional

import streamlit as st
from openai import OpenAI


DEFAULT_MODEL_ENV_VAR = "OPENAI_MODEL"
DEFAULT_MODEL_FALLBACK = "gpt-4o-mini"

# Part F4 -- one slow/hung request must never block a Stage 2/5 run for
# minutes. Explicit, centrally-configured request timeout and a small
# bounded retry count (never unbounded/infinite retry). Env-overridable so
# a slower task (e.g. a larger schema) can raise it without a code change.
DEFAULT_TIMEOUT_ENV_VAR = "LLM_REQUEST_TIMEOUT_SECONDS"
DEFAULT_TIMEOUT_SECONDS_FALLBACK = 20.0
DEFAULT_MAX_RETRIES_ENV_VAR = "LLM_REQUEST_MAX_RETRIES"
DEFAULT_MAX_RETRIES_FALLBACK = 1

_client_singleton: Optional[OpenAI] = None
_RESULT_CACHE: dict[str, Any] = {}


def resolve_timeout_seconds() -> float:
    """Centralized request timeout (seconds), overridable via
    LLM_REQUEST_TIMEOUT_SECONDS. Falls back to the hardcoded default on a
    missing/invalid env value rather than raising."""
    raw = (os.getenv(DEFAULT_TIMEOUT_ENV_VAR) or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS_FALLBACK
    try:
        value = float(raw)
        return value if value > 0 else DEFAULT_TIMEOUT_SECONDS_FALLBACK
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS_FALLBACK


def resolve_max_retries() -> int:
    """Bounded retry count for transient failures (timeout/rate-limit/
    connection errors) -- never unbounded. Overridable via
    LLM_REQUEST_MAX_RETRIES."""
    raw = (os.getenv(DEFAULT_MAX_RETRIES_ENV_VAR) or "").strip()
    if not raw:
        return DEFAULT_MAX_RETRIES_FALLBACK
    try:
        value = int(raw)
        return value if value >= 0 else DEFAULT_MAX_RETRIES_FALLBACK
    except ValueError:
        return DEFAULT_MAX_RETRIES_FALLBACK


def _is_transient_error(exc: Exception) -> bool:
    """Timeout/rate-limit/connection/server errors are worth one bounded
    retry; auth, bad-request, and schema errors are not (retrying them
    would just fail identically and burn the caller's time budget)."""
    type_name = type(exc).__name__.lower()
    message = str(exc).lower()
    return any(
        k in type_name or k in message
        for k in (
            "timeout", "timed out", "ratelimit", "rate_limit", "connection",
            "internalserver", "apistatuserror", "service_unavailable",
            "bad_gateway", "server_error",
        )
    )


def _streamlit_secret(name: str):
    """Read a Streamlit secret without requiring secrets.toml to exist."""
    try:
        value = st.secrets.get(name)
        return str(value).strip() if value else None
    except Exception:
        return None


def get_openai_client() -> OpenAI:
    """Environment-first client construction (required for CLI tools and
    GitHub Actions), falling back to Streamlit secrets for the deployed
    app -- the exact existing convention from llm_extractor.py, moved
    here as the single implementation.

    Cached as a process-level singleton: constructing an OpenAI client
    is cheap, but this avoids re-reading the key/env on every call.
    Tests that need a fresh client after patching env/secrets should
    call reset_client_singleton() first.
    """
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or _streamlit_secret(
        "OPENAI_API_KEY"
    )
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is missing. Configure an environment variable for "
            "CLI/GitHub Actions or a Streamlit secret for the app."
        )
    _client_singleton = OpenAI(api_key=api_key)
    return _client_singleton


def reset_client_singleton() -> None:
    """Test-only helper: forces the next get_openai_client() call to
    reconstruct the client (e.g. after patching env vars/secrets)."""
    global _client_singleton
    _client_singleton = None


def resolve_model(task_env_var: Optional[str] = None) -> str:
    """Project-wide default model (OPENAI_MODEL, defaulting to
    gpt-4o-mini) unless a task-specific override env var is set and
    non-empty. Generalizes the existing OPENAI_GATE_MODEL convention
    from llm_extractor.py to any task -- e.g. OPENAI_INTENT_MODEL,
    OPENAI_MECHANISM_MODEL -- without hardcoding a model name for any
    of them; every task falls back to OPENAI_MODEL when unset."""
    project_model = (os.getenv(DEFAULT_MODEL_ENV_VAR) or DEFAULT_MODEL_FALLBACK).strip()
    if task_env_var:
        override = (os.getenv(task_env_var) or "").strip()
        if override:
            return override
    return project_model


def _cache_key(
    task: str,
    model: str,
    normalized_input: str,
    schema_version: str,
    system_prompt_hash: str,
    schema_hash: str,
) -> str:
    digest = hashlib.sha256(
        f"{task}|{model}|{schema_version}|{system_prompt_hash}|{schema_hash}|{normalized_input}".encode("utf-8")
    ).hexdigest()
    return digest


def _stable_digest(text: str) -> str:
    """SHA-256 over the exact text -- stable across processes/restarts,
    unlike Python's process-randomized hash(). Used for both the
    system-prompt and schema components of the cache key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_schema_digest(schema: dict) -> str:
    """Deterministic serialization (sorted keys, no whitespace
    ambiguity) so semantically-identical schemas always hash the same,
    and any real schema change (new field, changed enum, etc.) always
    changes the digest -- this is what makes the cache key correct even
    when a developer forgets to bump schema_version (see Issue 3)."""
    serialized = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    return _stable_digest(serialized)


def clear_cache() -> None:
    """Test-only helper -- also useful for a long-lived process (e.g. a
    Streamlit server) that wants to force a fresh call after a prompt
    change without a redeploy, though the schema_version convention
    (see call_structured_json) is the normal way to invalidate a cache
    entry."""
    _RESULT_CACHE.clear()


def call_structured_json(
    *,
    system_prompt: str,
    user_content: str,
    schema: dict,
    schema_name: str,
    task: str = "generic",
    model_env_var: Optional[str] = None,
    schema_version: str = "v1",
    temperature: float = 0,
    use_cache: bool = True,
    deadline_seconds: Optional[float] = None,
) -> dict:
    """Call the Responses API with a strict json_schema output format and
    return the parsed JSON object.

    Centralizes:
    - model selection (resolve_model / model_env_var)
    - the "retry once against the project default model on a
      model-not-found error" fallback already used by
      llm_extractor.extract_gate_assertions_with_llm
    - an explicit request timeout (LLM_REQUEST_TIMEOUT_SECONDS, default
      20s) and a small bounded retry (LLM_REQUEST_MAX_RETRIES, default 1
      extra attempt) for transient failures only -- timeout/rate-limit/
      connection/server errors. A hung or slow request can never block
      the caller beyond timeout_seconds * (max_retries + 1) (part F4).
    - ``deadline_seconds`` (Part 17, Stage 2 remediation): an optional
      remaining-time budget from the CALLER's own deadline (e.g. Stage
      2's whole-stage wall-clock budget). When supplied, the per-attempt
      timeout is min(configured_request_timeout, remaining_seconds) --
      never the full configured timeout if less time than that remains
      -- and NO retry is attempted once the deadline itself has already
      passed (a retry is only worth attempting if there is still budget
      for it). deadline_seconds=None (the default) preserves the exact
      prior behavior for every caller that does not pass it.
    - a simple result cache keyed on (task, model, normalized input,
      schema_version, a stable hash of system_prompt, a stable hash of
      the schema) -- see module docstring's caching note and Issue 3's
      hardening: a changed system_prompt or schema always changes the
      cache key, even if the caller forgets to bump schema_version, so
      a stale cached result can never be returned for genuinely new
      prompt/schema content. A cache hit never re-calls the API. An
      exception is never cached, so a transient failure is retried on
      the caller's next attempt.

    Raises whatever the underlying SDK call raises on non-model-name
    errors (auth, rate limit, schema/prompt errors, malformed JSON via
    json.loads). Callers decide fail-open behavior -- this helper does
    not swallow errors itself (see module docstring).
    """
    model = resolve_model(model_env_var)
    project_model = (os.getenv(DEFAULT_MODEL_ENV_VAR) or DEFAULT_MODEL_FALLBACK).strip()

    cache_key = None
    if use_cache:
        cache_key = _cache_key(
            task, model, user_content, schema_version,
            _stable_digest(system_prompt), _stable_schema_digest(schema),
        )
        if cache_key in _RESULT_CACHE:
            return _RESULT_CACHE[cache_key]

    client = get_openai_client()
    request_kwargs = {
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": schema,
                "strict": True,
            }
        },
    }

    timeout_seconds = resolve_timeout_seconds()
    max_retries = resolve_max_retries()
    # Part 17 -- an external caller-supplied deadline caps the per-attempt
    # timeout and the retry budget. A monotonic absolute deadline
    # timestamp is computed once, here, at call time (not re-derived per
    # attempt from a relative "seconds remaining" that would otherwise
    # silently reset on every retry).
    call_deadline_ts = (
        time.monotonic() + deadline_seconds if deadline_seconds is not None else None
    )

    def _call(target_model: str, call_timeout: float):
        return client.responses.create(
            model=target_model, timeout=call_timeout, **request_kwargs
        )

    def _call_with_bounded_retry(target_model: str):
        # Small, bounded retry (never unbounded) for transient failures
        # only (part F4) -- an auth/schema/bad-request error is retried
        # zero times since it would just fail identically.
        attempts = max_retries + 1
        last_exc: Optional[Exception] = None
        for attempt in range(attempts):
            if call_deadline_ts is not None:
                remaining = call_deadline_ts - time.monotonic()
                if remaining <= 0:
                    # No stage budget left for even one more attempt
                    # (part 17: "do not allow a retry to exceed the
                    # remaining Stage 2 deadline"). Raise whatever we
                    # already have, or a clear timeout if this is the
                    # very first attempt and the deadline was already
                    # exhausted before starting.
                    raise last_exc or TimeoutError(
                        "No remaining Stage 2 budget for this LLM call"
                    )
                call_timeout = min(timeout_seconds, remaining)
            else:
                call_timeout = timeout_seconds
            try:
                return _call(target_model, call_timeout)
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts - 1 or not _is_transient_error(exc):
                    raise
        raise last_exc  # pragma: no cover -- unreachable, defensive only

    try:
        response = _call_with_bounded_retry(model)
    except Exception as exc:
        message = str(exc).lower()
        model_error = "model_not_found" in message or "does not exist" in message
        if not model_error or model == project_model:
            raise
        response = _call_with_bounded_retry(project_model)

    result = json.loads(response.output_text)
    if cache_key is not None:
        _RESULT_CACHE[cache_key] = result
    return result
