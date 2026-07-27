"""Stage 3: lease expiry and crash recovery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import queue

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_a_crashed_workers_job_is_reclaimed_after_the_lease_expires(session: Session) -> None:
    queue.enqueue(session, kind="x", payload={}, run_at=NOW)

    # w1 claims the job (30s lease), then "crashes" -- it never completes it.
    first = queue.claim(session, "w1", now=NOW, lease_seconds=30)
    assert first is not None
    assert first.locked_by == "w1"
    assert first.attempts == 1

    # While the lease is still valid, no other worker may take it.
    assert queue.claim(session, "w2", now=NOW + timedelta(seconds=5)) is None

    # Once the lease expires, w2 reclaims the very same job for another attempt.
    second = queue.claim(session, "w2", now=NOW + timedelta(seconds=31))
    assert second is not None
    assert second.id == first.id
    assert second.locked_by == "w2"
    assert second.attempts == 2
