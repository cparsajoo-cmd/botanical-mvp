"""Regression tests for the self-imposed per-run cost ceiling added to
ai_usage_telemetry.py (2026-08-29 chat session).

Per-task call-count limits (AIRunTracker.set_limit) bound how many times
ONE task can call the model, but say nothing about total spend across every
task in a run. This adds a genuine total-cost circuit breaker: once the
running estimated cost (priced calls only) crosses a configurable ceiling,
the run's existing circuit-breaker mechanism trips, so every further call
-- for any task -- is skipped for the rest of the run, exactly like an
insufficient_quota provider error already does.
"""
import os

import pytest

from ai_usage_telemetry import (
    AIRunTracker,
    ERROR_RUN_COST_CEILING,
    RUN_COST_CEILING_ENV_VAR,
    DEFAULT_RUN_COST_CEILING_USD_FALLBACK,
    resolve_run_cost_ceiling_usd,
)


def _record_priced_call(tracker: AIRunTracker, task: str, *, input_tokens: int, output_tokens: int, model: str = "gpt-4o"):
    tracker.record_call(
        task, cached=False, success=True,
        input_tokens=input_tokens, output_tokens=output_tokens, model=model,
    )


def test_no_ceiling_by_default_unbounded_calls_allowed():
    tracker = AIRunTracker(managed_run=True)
    for _ in range(5):
        _record_priced_call(tracker, "evidence_adjudication", input_tokens=100_000, output_tokens=50_000)
    assert not tracker.breaker_active()


def test_ceiling_trips_breaker_once_crossed():
    tracker = AIRunTracker(managed_run=True)
    tracker.set_run_cost_ceiling_usd(0.01)
    # gpt-4o: $2.50/M input + $10/M output -> well over $0.01 in one call
    # with these token counts.
    _record_priced_call(tracker, "evidence_adjudication", input_tokens=2000, output_tokens=1000)
    assert tracker.breaker_active()
    assert tracker.breaker_category == ERROR_RUN_COST_CEILING


def test_ceiling_does_not_trip_before_crossed():
    tracker = AIRunTracker(managed_run=True)
    tracker.set_run_cost_ceiling_usd(10.00)
    _record_priced_call(tracker, "evidence_adjudication", input_tokens=100, output_tokens=50)
    assert not tracker.breaker_active()


def test_once_tripped_further_calls_are_skipped_via_llm_client_pattern():
    """Mirrors the actual enforcement point: llm_client.call_structured_json
    checks tracker.breaker_active() BEFORE every request and raises rather
    than calling the provider once the breaker is open."""
    tracker = AIRunTracker(managed_run=True)
    tracker.set_run_cost_ceiling_usd(0.01)
    _record_priced_call(tracker, "evidence_adjudication", input_tokens=2000, output_tokens=1000)
    assert tracker.breaker_active()
    tracker.record_skipped_breaker("mechanistic_reasoning")
    summary = tracker.summary()
    assert summary["total_skipped_breaker"] == 1
    assert summary["provider_circuit_category"] == ERROR_RUN_COST_CEILING


def test_zero_or_negative_ceiling_disables_the_check():
    tracker = AIRunTracker(managed_run=True)
    tracker.set_run_cost_ceiling_usd(0)
    _record_priced_call(tracker, "evidence_adjudication", input_tokens=1_000_000, output_tokens=1_000_000)
    assert not tracker.breaker_active()
    assert tracker.get_run_cost_ceiling_usd() is None


def test_unpriced_model_override_never_trips_the_ceiling():
    tracker = AIRunTracker(managed_run=True)
    tracker.set_run_cost_ceiling_usd(0.0001)
    tracker.record_call(
        "evidence_adjudication", cached=False, success=True,
        input_tokens=1_000_000, output_tokens=1_000_000, model="some-future-unpriced-model",
    )
    # Cost for an unlisted model is never guessed -- the ceiling can only
    # ever be crossed by a call whose cost was actually computed.
    assert not tracker.breaker_active()


def test_summary_exposes_the_configured_ceiling():
    tracker = AIRunTracker(managed_run=True)
    tracker.set_run_cost_ceiling_usd(0.75)
    assert tracker.summary()["run_cost_ceiling_usd"] == 0.75


def test_resolve_run_cost_ceiling_usd_env_override(monkeypatch):
    monkeypatch.setenv(RUN_COST_CEILING_ENV_VAR, "2.50")
    assert resolve_run_cost_ceiling_usd() == 2.50


def test_resolve_run_cost_ceiling_usd_falls_back_on_invalid_value(monkeypatch):
    monkeypatch.setenv(RUN_COST_CEILING_ENV_VAR, "not-a-number")
    assert resolve_run_cost_ceiling_usd() == DEFAULT_RUN_COST_CEILING_USD_FALLBACK


def test_resolve_run_cost_ceiling_usd_env_zero_disables(monkeypatch):
    monkeypatch.setenv(RUN_COST_CEILING_ENV_VAR, "0")
    assert resolve_run_cost_ceiling_usd() is None


def test_resolve_run_cost_ceiling_usd_default_when_unset(monkeypatch):
    monkeypatch.delenv(RUN_COST_CEILING_ENV_VAR, raising=False)
    assert resolve_run_cost_ceiling_usd() == DEFAULT_RUN_COST_CEILING_USD_FALLBACK


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
