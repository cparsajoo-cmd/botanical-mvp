import math

from ai_usage_telemetry import AIRunTracker


def test_gpt4o_mini_cost_tracks_uncached_cached_and_output_tokens():
    tracker = AIRunTracker(managed_run=True)
    tracker.record_call(
        "evidence_adjudication",
        cached=False,
        success=True,
        input_tokens=1_000_000,
        cached_input_tokens=200_000,
        output_tokens=100_000,
        model="gpt-4o-mini",
    )
    summary = tracker.summary()
    # 800k uncached * $0.15/M + 200k cached * $0.075/M + 100k out * $0.60/M
    assert math.isclose(summary["estimated_cost_usd"], 0.195, rel_tol=0, abs_tol=1e-12)
    assert summary["total_input_tokens"] == 1_000_000
    assert summary["total_cached_input_tokens"] == 200_000
    assert summary["total_output_tokens"] == 100_000


def test_embedding_cost_is_included():
    tracker = AIRunTracker(managed_run=True)
    tracker.record_call(
        "embedding_query",
        cached=False,
        success=True,
        input_tokens=500_000,
        model="text-embedding-3-small",
    )
    summary = tracker.summary()
    assert math.isclose(summary["estimated_cost_usd"], 0.01, rel_tol=0, abs_tol=1e-12)


def test_unknown_model_is_not_guessed():
    tracker = AIRunTracker(managed_run=True)
    tracker.record_call(
        "evidence_synthesis",
        cached=False,
        success=True,
        input_tokens=1000,
        output_tokens=100,
        model="some-future-model",
    )
    summary = tracker.summary()
    assert summary["estimated_cost_usd"] is None
    assert summary["unpriced_models"] == ["some-future-model"]
    assert summary["priced_cost_usd"] == 0.0
