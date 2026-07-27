"""A worker: claim a job, run the handler for its kind, then complete it -- or, if the
handler raises, hand the job to the retry/dead-letter path instead of crashing."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app import queue
from app.models import Job, utcnow

Handler = Callable[[dict[str, object]], None]


def process_one(
    session: Session,
    worker_id: str,
    handlers: dict[str, Handler],
    *,
    now: datetime | None = None,
) -> Job | None:
    """Claim and run one job. Returns the job (whatever its outcome), or None if
    nothing was due."""
    now = now or utcnow()
    job = queue.claim(session, worker_id, now=now)
    if job is None:
        return None
    try:
        handlers[job.kind](json.loads(job.payload_json))
    except Exception as exc:  # noqa: BLE001 - a failing handler must retry/dead-letter, not crash
        queue.fail(session, job, error=repr(exc), now=now)
        return job
    queue.complete(session, job)
    return job
