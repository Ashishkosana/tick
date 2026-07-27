"""The durable queue.

`claim` is the heart of it: select the next eligible job and lock its row with
SELECT ... FOR UPDATE SKIP LOCKED (on Postgres), so many workers can pull work at
once and never grab the same row. A job is eligible if it is pending and due, OR if
it is leased but its lease has expired -- that second case is how a crashed worker's
job gets reclaimed. On SQLite (single-threaded tests) the row lock is a no-op.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app import retry
from app.models import Job, utcnow


def enqueue(
    session: Session,
    *,
    kind: str,
    payload: dict[str, object],
    run_at: datetime | None = None,
    max_attempts: int = 3,
    interval_seconds: int | None = None,
) -> Job:
    """Add a job. `run_at` in the future schedules it; `interval_seconds` makes it
    recurring (a new occurrence is enqueued each time it completes)."""
    job = Job(
        id=uuid.uuid4().hex,
        kind=kind,
        payload_json=json.dumps(payload),
        state="pending",
        run_at=run_at or utcnow(),
        max_attempts=max_attempts,
        interval_seconds=interval_seconds,
    )
    session.add(job)
    session.commit()
    return job


def claim(
    session: Session, worker_id: str, *, now: datetime | None = None, lease_seconds: int = 30
) -> Job | None:
    """Atomically take the next due (or crashed-and-expired) job and lease it."""
    now = now or utcnow()
    stmt = (
        select(Job)
        .where(
            Job.run_at <= now,
            or_(
                Job.state == "pending",
                and_(Job.state == "leased", Job.lease_until < now),  # expired lease -> reclaim
            ),
        )
        .order_by(Job.run_at)
        .limit(1)
    )
    if session.get_bind().dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    job = session.scalars(stmt).first()
    if job is None:
        return None
    job.state = "leased"
    job.locked_by = worker_id
    job.attempts += 1
    job.lease_until = now + timedelta(seconds=lease_seconds)
    session.commit()
    return job


def complete(session: Session, job: Job) -> Job | None:
    """Mark a leased job done. If it is recurring, enqueue the next occurrence and
    return it; otherwise return None."""
    job.state = "done"
    job.locked_by = None
    job.lease_until = None
    successor: Job | None = None
    if job.interval_seconds is not None:
        successor = Job(
            id=uuid.uuid4().hex,
            kind=job.kind,
            payload_json=job.payload_json,
            state="pending",
            run_at=job.run_at + timedelta(seconds=job.interval_seconds),
            max_attempts=job.max_attempts,
            interval_seconds=job.interval_seconds,
        )
        session.add(successor)
    session.commit()
    return successor


def fail(session: Session, job: Job, *, error: str, now: datetime | None = None) -> None:
    """Reschedule a failed job with exponential backoff, or dead-letter it once it has
    used up `max_attempts`."""
    now = now or utcnow()
    job.locked_by = None
    job.lease_until = None
    job.last_error = error
    if job.attempts >= job.max_attempts:
        job.state = "dead"
    else:
        job.state = "pending"
        job.run_at = now + timedelta(seconds=retry.backoff_delay(job.attempts))
    session.commit()
