"""Stage 2: retries, exponential backoff, and the dead-letter state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app import queue, worker
from app.retry import backoff_delay

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _boom(_: dict[str, object]) -> None:
    raise RuntimeError("boom")


def test_backoff_is_exponential_and_capped() -> None:
    assert backoff_delay(1) == pytest.approx(0.1)
    assert backoff_delay(2) == pytest.approx(0.2)
    assert backoff_delay(3) == pytest.approx(0.4)
    assert backoff_delay(10, cap=1.0) == pytest.approx(1.0)


def test_a_failed_job_reschedules_with_backoff(session: Session) -> None:
    queue.enqueue(session, kind="x", payload={}, run_at=NOW, max_attempts=3)
    job = worker.process_one(session, "w1", {"x": _boom}, now=NOW)
    assert job is not None
    assert job.state == "pending"  # rescheduled, not dead
    assert job.attempts == 1
    assert job.run_at > NOW  # pushed into the future by backoff


def test_a_job_dead_letters_after_max_attempts(session: Session) -> None:
    queue.enqueue(session, kind="x", payload={}, run_at=NOW, max_attempts=2)
    worker.process_one(session, "w1", {"x": _boom}, now=NOW + timedelta(seconds=10))
    job = worker.process_one(session, "w1", {"x": _boom}, now=NOW + timedelta(seconds=20))
    assert job is not None
    assert job.state == "dead"
    assert job.attempts == 2
    assert "boom" in (job.last_error or "")
