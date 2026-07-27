"""Stage 4: recurring (fixed-interval) schedules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import queue

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_completing_a_recurring_job_schedules_the_next_occurrence(session: Session) -> None:
    queue.enqueue(session, kind="beat", payload={"n": 1}, run_at=NOW, interval_seconds=60)
    job = queue.claim(session, "w1", now=NOW)
    assert job is not None
    successor = queue.complete(session, job)
    assert job.state == "done"
    assert successor is not None
    assert successor.state == "pending"
    # next occurrence is exactly one interval after this one's scheduled time
    assert successor.run_at == job.run_at + timedelta(seconds=60)
    assert successor.interval_seconds == 60


def test_a_one_shot_job_has_no_successor(session: Session) -> None:
    queue.enqueue(session, kind="once", payload={}, run_at=NOW)
    job = queue.claim(session, "w1", now=NOW)
    assert job is not None
    assert queue.complete(session, job) is None
