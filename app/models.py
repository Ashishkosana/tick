"""ORM tables.

A job's whole lifecycle lives in one row. `state` is a plain string; the transition
rules and the concurrency-safe claiming live in app/queue.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Job(Base):
    """A unit of work.

    States: pending -> leased -> done, or -> failed -> (retry) pending, or -> dead
    after max_attempts. `run_at` is when the job becomes eligible (future = a
    scheduled job). `lease_until` / `locked_by` record which worker holds it and for
    how long, so a crashed worker's job can be reclaimed once the lease expires.
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    state: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
