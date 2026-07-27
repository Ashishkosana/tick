"""Retry backoff (exponential, capped, with optional jitter).

Spacing retries out avoids hammering a struggling dependency; jitter spreads a fleet
of workers so they don't all retry at the same instant. The jitter fraction is passed
in, so this stays a pure, testable function.
"""

from __future__ import annotations


def backoff_delay(
    attempt: int, *, base: float = 0.1, factor: float = 2.0, cap: float = 30.0, jitter: float = 0.0
) -> float:
    """Seconds to wait before retry `attempt` (1-based)."""
    raw = min(base * (factor ** (attempt - 1)), cap)
    return raw + raw * jitter
