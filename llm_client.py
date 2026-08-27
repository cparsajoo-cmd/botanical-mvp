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
from typing import Any, Optional

import streamlit as st
from openai import OpenAI


DEFAULT_MODEL_ENV_VAR = "OPENAI_MODEL"
DEFAULT_MODEL_FALLBACK = "gpt-4o-mini"

_client_singleton: Optional[OpenAI] = None
_RESULT_CACHE: dict[str, Any] = {}


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


def _cache_key(task: str, model: str, normalized_input: str, schema_version: str) -> str:
    digest = hashlib.sha256(
        f"{task}|{model}|{schema_version}|{normalized_input}".encode("utf-8")
    ).hexdigest()
    return digest


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
) -> dict:
    """Call the Responses API with a strict json_schema output format and
    return the parsed JSON object.

    Centralizes:
    - model selection (resolve_model / model_env_var)
    - the "retry once against the project default model on a
      model-not-found error" fallback already used by
      llm_extractor.extract_gate_assertions_with_llm
    - a simple result cache keyed on (task, model, normalized input,
      schema_version) -- see module docstring's caching note. A cache
      hit never re-calls the API. An exception is never cached, so a
      transient failure is retried on the caller's next attempt.

    Raises whatever the underlying SDK call raises on non-model-name
    errors (auth, rate limit, schema/prompt errors, malformed JSON via
    json.loads). Callers decide fail-open behavior -- this helper does
    not swallow errors itself (see module docstring).
    """
    model = resolve_model(model_env_var)
    project_model = (os.getenv(DEFAULT_MODEL_ENV_VAR) or DEFAULT_MODEL_FALLBACK).strip()

    cache_key = None
    if use_cache:
        cache_key = _cache_key(task, model, user_content, schema_version)
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

    try:
        response = client.responses.create(model=model, **request_kwargs)
    except Exception as exc:
        message = str(exc).lower()
        model_error = "model_not_found" in message or "does not exist" in message
        if not model_error or model == project_model:
            raise
        response = client.responses.create(model=project_model, **request_kwargs)

    result = json.loads(response.output_text)
    if cache_key is not None:
        _RESULT_CACHE[cache_key] = result
    return result
