"""Stage 1: the durable queue -- enqueue, claim, complete."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app import queue, worker
from app.models import Job

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_enqueue_creates_a_pending_job(session: Session) -> None:
    job = queue.enqueue(session, kind="email", payload={"to": "x"})
    assert job.state == "pending"
    assert session.query(Job).count() == 1


def test_claim_returns_a_due_job_and_leases_it(session: Session) -> None:
    queue.enqueue(session, kind="email", payload={}, run_at=NOW)
    job = queue.claim(session, "w1", now=NOW + timedelta(seconds=1))
    assert job is not None
    assert job.state == "leased"
    assert job.locked_by == "w1"
    assert job.attempts == 1


def test_claim_skips_jobs_scheduled_for_the_future(session: Session) -> None:
    queue.enqueue(session, kind="email", payload={}, run_at=NOW + timedelta(minutes=5))
    assert queue.claim(session, "w1", now=NOW) is None


def test_claim_on_empty_queue_returns_none(session: Session) -> None:
    assert queue.claim(session, "w1", now=NOW) is None


def test_a_leased_job_is_not_claimed_again(session: Session) -> None:
    queue.enqueue(session, kind="email", payload={}, run_at=NOW)
    first = queue.claim(session, "w1", now=NOW + timedelta(seconds=1))
    second = queue.claim(session, "w2", now=NOW + timedelta(seconds=1))
    assert first is not None
    assert second is None  # the only job is already leased


def test_claim_is_earliest_run_at_first(session: Session) -> None:
    queue.enqueue(session, kind="later", payload={}, run_at=NOW + timedelta(seconds=2))
    queue.enqueue(session, kind="sooner", payload={}, run_at=NOW + timedelta(seconds=1))
    job = queue.claim(session, "w1", now=NOW + timedelta(seconds=5))
    assert job is not None
    assert job.kind == "sooner"


def test_complete_marks_the_job_done(session: Session) -> None:
    queue.enqueue(session, kind="email", payload={}, run_at=NOW)
    job = queue.claim(session, "w1", now=NOW + timedelta(seconds=1))
    assert job is not None
    queue.complete(session, job)
    assert job.state == "done"


def test_worker_processes_a_job_end_to_end(session: Session) -> None:
    queue.enqueue(session, kind="greet", payload={"name": "ash"}, run_at=NOW)
    seen: list[dict[str, object]] = []
    handlers = {"greet": seen.append}
    job = worker.process_one(session, "w1", handlers, now=NOW + timedelta(seconds=1))
    assert job is not None
    assert job.state == "done"
    assert seen == [{"name": "ash"}]
