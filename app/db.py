"""Database plumbing: engine, session factory, declarative Base.

The URL is configurable so unit tests run on SQLite with zero infra, while the
SKIP LOCKED concurrency demo runs against Postgres (docker-compose.yml).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("TICK_DB", "sqlite:///tick.db")


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  (import registers the tables on Base)

    Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
