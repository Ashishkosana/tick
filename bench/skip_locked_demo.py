"""SKIP LOCKED concurrency demo.

Enqueue N jobs, then run M worker threads that each loop claiming + completing until
the queue drains. It proves the core guarantee: every job is processed EXACTLY once
and no two workers ever claim the same job -- which is what FOR UPDATE SKIP LOCKED buys
you, with no external lock service.

Run against Postgres:
    docker compose up -d db
    TICK_DB=postgresql+psycopg://tick:tick@localhost:5434/tick python bench/skip_locked_demo.py
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models  # noqa: E402,F401  (registers tables)
from app import queue  # noqa: E402
from app.db import Base  # noqa: E402
from app.models import Job, utcnow  # noqa: E402

URL = os.environ.get("TICK_DB", "sqlite:///bench.db")
_kw = {"pool_size": 30, "max_overflow": 60} if not URL.startswith("sqlite") else {}
engine = create_engine(URL, future=True, **_kw)
Session = sessionmaker(bind=engine, expire_on_commit=False)


def _reset_and_seed(n: int) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as s:
        now = utcnow()
        for i in range(n):
            queue.enqueue(s, kind="work", payload={"i": i}, run_at=now)


def _worker_loop(worker_id: str, now: "object") -> list[str]:
    processed: list[str] = []
    with Session() as s:
        while True:
            job = queue.claim(s, worker_id, now=now)  # type: ignore[arg-type]
            if job is None:
                break
            queue.complete(s, job)
            processed.append(job.id)
    return processed


def main(n: int = 500, workers: int = 10) -> None:
    _reset_and_seed(n)
    now = utcnow()
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda w: _worker_loop(f"w{w}", now), range(workers)))
    elapsed = time.perf_counter() - start

    all_ids = [jid for r in results for jid in r]
    counts = Counter(all_ids)
    duplicates = [jid for jid, c in counts.items() if c > 1]
    with Session() as s:
        done = s.scalar(select(func.count()).select_from(Job).where(Job.state == "done"))
    split = {f"w{i}": len(results[i]) for i in range(workers)}

    print(f"DB: {URL}")
    print(f"[skip-locked] {n} jobs, {workers} workers")
    print(f"  processed total: {len(all_ids)} | unique: {len(counts)} | duplicates: {len(duplicates)}")
    print(f"  done in DB: {done} | {elapsed:.2f}s -> {n / elapsed:.0f} jobs/s")
    print(f"  work split: {split}")
    assert not duplicates, f"COLLISION: {len(duplicates)} job(s) claimed by 2+ workers!"
    assert done == n and len(counts) == n, "not every job was processed exactly once"
    print("OK - every job processed exactly once, zero collisions")


if __name__ == "__main__":
    main(500, 10)
