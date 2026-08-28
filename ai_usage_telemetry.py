"""Central OpenAI usage governance.

The tracker is context-local (ContextVar), not process-global, so concurrent
Streamlit sessions/runs cannot reset or trip one another's breaker.  It records
logical calls separately from actual provider attempts so the run summary can
be reconciled with provider dashboard request counts.
"""
from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field
from typing import Optional

ERROR_INSUFFICIENT_QUOTA = "insufficient_quota"
ERROR_AUTH = "authentication_failure"
ERROR_RATE_LIMIT = "rate_limit"
ERROR_TIMEOUT = "timeout"
ERROR_CONNECTION = "connection_failure"
ERROR_INVALID_OUTPUT = "malformed_model_output"
ERROR_OTHER = "other"
BREAKER_TRIPPING_CATEGORIES = frozenset({ERROR_INSUFFICIENT_QUOTA, ERROR_AUTH})


def classify_llm_error(exc: BaseException) -> str:
    type_name = type(exc).__name__.lower()
    message = str(exc).lower()
    def _has(*keys: str) -> bool:
        return any(k in type_name or k in message for k in keys)
    if _has("insufficient_quota", "credit_balance_exhausted", "billing_hard_limit", "exceeded your current quota"):
        return ERROR_INSUFFICIENT_QUOTA
    if _has("authenticationerror", "invalid_api_key", "unauthorized", "permissiondenied", "incorrect api key", "invalid_request_error: api key"):
        return ERROR_AUTH
    if _has("ratelimit", "rate_limit", "429", "toomanyrequests"):
        return ERROR_RATE_LIMIT
    if _has("timeout", "timed out"):
        return ERROR_TIMEOUT
    if _has("connectionerror", "connection error", "network", "apiconnectionerror"):
        return ERROR_CONNECTION
    if _has("jsondecodeerror", "malformed", "invalid json", "invalid_schema", "valueerror"):
        return ERROR_INVALID_OUTPUT
    return ERROR_OTHER


class AIBudgetExhaustedError(Exception):
    def __init__(self, task: str, limit: int):
        self.task, self.limit = task, limit
        super().__init__(f"AI_BUDGET_EXHAUSTED: task '{task}' reached its per-run limit of {limit} call(s); using deterministic fallback.")


class AIProviderCircuitOpenError(Exception):
    def __init__(self, category: str, reason: str = ""):
        self.category = category
        self.reason = reason or category
        # Backward compatible exception detail for internal logs/tests. UI/export
        # code must use the sanitized category from summary(), never this text.
        super().__init__(f"AI_PROVIDER_UNAVAILABLE ({category}): {self.reason} -- circuit open for the rest of this run.")


@dataclass
class _TaskStats:
    calls: int = 0                 # logical provider-backed calls
    provider_attempts: int = 0     # every actual SDK request
    cached_hits: int = 0
    failures: int = 0
    retries: int = 0
    model_fallback_attempts: int = 0
    skipped_budget: int = 0
    skipped_breaker: int = 0
    elapsed_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    # Provider-billed token usage keyed by the actual model used.  This is
    # deliberately separate from application-level cached_hits: OpenAI prompt
    # caching can still bill discounted cached input tokens on a real request.
    model_usage: dict = field(default_factory=dict)
    errors_by_category: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "provider_attempts": self.provider_attempts,
            "cached_hits": self.cached_hits,
            "failures": self.failures,
            "retries": self.retries,
            "model_fallback_attempts": self.model_fallback_attempts,
            "skipped_budget": self.skipped_budget,
            "skipped_breaker": self.skipped_breaker,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "model_usage": {k: dict(v) for k, v in self.model_usage.items()},
            "errors_by_category": dict(self.errors_by_category),
        }


# API token prices in USD per 1M tokens, verified against OpenAI's model
# pricing pages on 2026-08-28.  Cost is intentionally reported as an
# *estimate*: taxes/credits/account adjustments are not represented here.
# Unknown model overrides are never guessed; they are flagged as unpriced.
_MODEL_PRICING_USD_PER_MILLION = {
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-2024-11-20": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "text-embedding-3-small": {"input": 0.02, "cached_input": 0.02, "output": 0.0},
}

def _estimate_model_cost_usd(model: str, usage: dict) -> Optional[float]:
    rates = _MODEL_PRICING_USD_PER_MILLION.get(str(model or ""))
    if not rates:
        return None
    total_input = max(0, int((usage or {}).get("input_tokens", 0) or 0))
    cached_input = min(total_input, max(0, int((usage or {}).get("cached_input_tokens", 0) or 0)))
    uncached_input = total_input - cached_input
    output = max(0, int((usage or {}).get("output_tokens", 0) or 0))
    return (
        uncached_input * rates["input"]
        + cached_input * rates["cached_input"]
        + output * rates["output"]
    ) / 1_000_000.0

def _task_cost_summary(stats: _TaskStats) -> dict:
    priced = 0.0
    unpriced_models = []
    by_model = {}
    for model, usage in stats.model_usage.items():
        cost = _estimate_model_cost_usd(model, usage)
        by_model[model] = {**dict(usage), "estimated_cost_usd": cost}
        if cost is None:
            unpriced_models.append(model)
        else:
            priced += cost
    return {
        "estimated_cost_usd": priced if not unpriced_models else None,
        "priced_cost_usd": priced,
        "unpriced_models": sorted(unpriced_models),
        "models": by_model,
    }


class AIRunTracker:
    def __init__(self, run_id: Optional[str] = None, *, managed_run: bool = False):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        # True only for an explicitly started Stage 2/Stage 5 (or other
        # governed) run.  Implicit trackers keep direct library/test calls
        # observable without leaking a circuit-breaker failure into unrelated
        # later calls that happen to share the same Python context.
        self.managed_run = bool(managed_run)
        self._tasks: dict[str, _TaskStats] = {}
        self._limits: dict[str, int] = {}
        self.breaker_tripped = False
        self.breaker_category: Optional[str] = None
        # Raw reason is internal-only; summary() deliberately sanitizes it.
        self.breaker_reason: Optional[str] = None

    def _stats(self, task: str) -> _TaskStats:
        return self._tasks.setdefault(task, _TaskStats())

    def set_limit(self, task: str, max_calls: Optional[int]) -> None:
        if max_calls is None:
            self._limits.pop(task, None)
        else:
            self._limits[task] = max(0, int(max_calls))

    def get_limit(self, task: str) -> Optional[int]:
        return self._limits.get(task)

    def check_budget(self, task: str) -> bool:
        limit = self._limits.get(task)
        stats = self._stats(task)
        if limit is not None and stats.calls >= limit:
            stats.skipped_budget += 1
            return False
        return True

    def breaker_active(self) -> bool:
        return self.breaker_tripped

    def trip_breaker(self, category: str, reason: str = "") -> None:
        if self.breaker_tripped:
            return
        self.breaker_tripped = True
        self.breaker_category = category
        self.breaker_reason = reason or category

    def record_skipped_breaker(self, task: str) -> None:
        self._stats(task).skipped_breaker += 1

    def record_provider_attempt(self, task: str, *, retry: bool = False, model_fallback: bool = False) -> None:
        stats = self._stats(task)
        stats.provider_attempts += 1
        if retry:
            stats.retries += 1
        if model_fallback:
            stats.model_fallback_attempts += 1

    def record_call(self, task: str, *, cached: bool, success: bool,
                    elapsed_seconds: float = 0.0, retries: int = 0,
                    error_category: Optional[str] = None,
                    input_tokens: int = 0, output_tokens: int = 0,
                    cached_input_tokens: int = 0, model: Optional[str] = None) -> None:
        stats = self._stats(task)
        if cached:
            stats.cached_hits += 1
            return
        stats.calls += 1
        stats.elapsed_seconds += elapsed_seconds
        # Legacy callers may still report retry count here. Avoid double-counting
        # when provider attempts have already recorded retries.
        if retries and stats.provider_attempts == 0:
            stats.retries += retries
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        cached_input_tokens = min(input_tokens, max(0, int(cached_input_tokens or 0)))
        stats.input_tokens += input_tokens
        stats.output_tokens += output_tokens
        stats.cached_input_tokens += cached_input_tokens
        if model and (input_tokens or output_tokens):
            bucket = stats.model_usage.setdefault(
                str(model), {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
            )
            bucket["input_tokens"] += input_tokens
            bucket["cached_input_tokens"] += cached_input_tokens
            bucket["output_tokens"] += output_tokens
        if not success:
            stats.failures += 1
            if error_category:
                stats.errors_by_category[error_category] = stats.errors_by_category.get(error_category, 0) + 1

    def summary(self) -> dict:
        tasks = {}
        priced_total = 0.0
        unpriced_models = set()
        for task, stats in self._tasks.items():
            task_data = stats.as_dict()
            cost_data = _task_cost_summary(stats)
            task_data.update(cost_data)
            tasks[task] = task_data
            priced_total += float(cost_data.get("priced_cost_usd", 0.0) or 0.0)
            unpriced_models.update(cost_data.get("unpriced_models") or [])
        logical = sum(s.calls for s in self._tasks.values())
        attempts = sum(s.provider_attempts for s in self._tasks.values())
        return {
            "run_id": self.run_id,
            "provider_circuit_open": self.breaker_tripped,
            "provider_circuit_category": self.breaker_category,
            "provider_circuit_reason": self.breaker_category if self.breaker_tripped else None,
            "tasks": tasks,
            # Backward-compatible alias; new code should prefer total_logical_calls.
            "total_api_calls": logical,
            "total_logical_calls": logical,
            "total_provider_attempts": attempts,
            "total_cached_hits": sum(s.cached_hits for s in self._tasks.values()),
            "total_failures": sum(s.failures for s in self._tasks.values()),
            "total_skipped_budget": sum(s.skipped_budget for s in self._tasks.values()),
            "total_skipped_breaker": sum(s.skipped_breaker for s in self._tasks.values()),
            "total_input_tokens": sum(s.input_tokens for s in self._tasks.values()),
            "total_cached_input_tokens": sum(s.cached_input_tokens for s in self._tasks.values()),
            "total_output_tokens": sum(s.output_tokens for s in self._tasks.values()),
            "estimated_cost_usd": priced_total if not unpriced_models else None,
            "priced_cost_usd": priced_total,
            "unpriced_models": sorted(unpriced_models),
            "cost_estimate_note": (
                "Token-price estimate only; excludes taxes, credits, and account adjustments. "
                "Unknown model overrides are not guessed."
            ),
        }

    def task_status_label(self, task: str) -> str:
        stats = self._tasks.get(task)
        if stats is None:
            return "NOT_RUN"
        successes = stats.calls - stats.failures
        if successes > 0:
            return "OK" if stats.failures == 0 else "FALLBACK"
        if stats.calls == 0 and stats.cached_hits > 0:
            return "OK"
        if stats.skipped_breaker > 0 or stats.skipped_budget > 0 or stats.failures > 0:
            return "UNAVAILABLE"
        return "NOT_RUN"


_tracker_var: contextvars.ContextVar[Optional[AIRunTracker]] = contextvars.ContextVar("ai_run_tracker", default=None)


def get_ai_run_tracker() -> AIRunTracker:
    tracker = _tracker_var.get()
    if tracker is None:
        tracker = AIRunTracker(managed_run=False)
        _tracker_var.set(tracker)
    return tracker


def start_new_ai_run(run_id: Optional[str] = None) -> AIRunTracker:
    tracker = AIRunTracker(run_id, managed_run=True)
    _tracker_var.set(tracker)
    return tracker


def reset_ai_run_context() -> AIRunTracker:
    """Reset the current context to an *implicit*, unmanaged tracker.

    Intended for test/library boundaries that deliberately clear LLM caches.
    Interactive Stage 2/Stage 5 code should use :func:`start_new_ai_run` so
    quota/auth failures trip a circuit breaker for that explicit run.
    """
    tracker = AIRunTracker(managed_run=False)
    _tracker_var.set(tracker)
    return tracker
