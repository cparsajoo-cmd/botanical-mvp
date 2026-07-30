"""Small process-local guard for connectors that receive HTTP 429.

The guard prevents a Streamlit collection run from repeatedly hammering an
upstream service after it has explicitly rate-limited the process. State is
process-local and intentionally not persisted.
"""
from __future__ import annotations

import random
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Mapping, Optional


class RateLimitUnavailable(RuntimeError):
    """Raised when an upstream source is temporarily unavailable due to 429."""


class ProcessRateLimitGuard:
    def __init__(self, source_name: str, default_cooldown_seconds: float = 60.0):
        self.source_name = source_name
        self.default_cooldown_seconds = max(1.0, float(default_cooldown_seconds))
        self._blocked_until = 0.0
        self._lock = threading.Lock()

    def remaining_seconds(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - time.monotonic())

    def ensure_available(self) -> None:
        remaining = self.remaining_seconds()
        if remaining > 0:
            raise RateLimitUnavailable(
                f"{self.source_name} temporarily unavailable due to rate limit "
                f"(HTTP 429); process-local cooldown has {remaining:.0f}s remaining."
            )

    def block(self, seconds: float) -> None:
        seconds = max(1.0, float(seconds))
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.monotonic() + seconds)


def retry_after_seconds(
    headers: Optional[Mapping[str, str]],
    *,
    fallback_seconds: float,
    maximum_seconds: float = 120.0,
) -> float:
    """Parse Retry-After seconds or HTTP date, with bounded jitter."""
    raw = (headers or {}).get("Retry-After")
    seconds = None
    if raw:
        try:
            seconds = float(raw)
        except (TypeError, ValueError):
            try:
                retry_dt = parsedate_to_datetime(str(raw))
                now = time.time()
                seconds = retry_dt.timestamp() - now
            except Exception:
                seconds = None

    if seconds is None or seconds <= 0:
        seconds = float(fallback_seconds)

    # Small jitter keeps concurrent workers from retrying at the same instant.
    seconds *= random.uniform(0.9, 1.1)
    return min(maximum_seconds, max(1.0, seconds))
