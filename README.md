# tick

A durable job & cron scheduler backed by a single Postgres table. Many workers pull
work concurrently without ever running the same job twice, jobs survive worker
crashes, and failures retry with backoff before landing in a dead-letter state.

## The problem it solves

"Run this later" / "run this every night" is deceptively hard once you care about
correctness:

- If two workers poll the same table, they can grab the **same job** and run it twice.
- If a worker **crashes mid-job**, is the job lost, or stuck "in progress" forever?
- A **poison job** that always fails can retry forever and block the queue.

`tick` solves these on plain Postgres — no Redis, no broker, no external lock service.

## What it does

- **Concurrent-safe claiming** — the next due job is taken with
  `SELECT ... FOR UPDATE SKIP LOCKED`, so N workers pull work in parallel and never
  collide on the same row.
- **Leasing + crash recovery** — a claimed job is leased to a worker for a TTL; if the
  worker dies, the lease expires and another worker reclaims it (at-least-once).
- **Retries, backoff, and a dead-letter state** — a failing job retries with
  exponential backoff and, after `max_attempts`, is parked as `dead` for triage.
- **Scheduling** — `run_at` in the future makes a job a scheduled/cron job.

## Architecture

```
app/
  db.py       connection + session (plumbing)
  models.py   the jobs table (whole lifecycle in one row)
  queue.py    enqueue / claim (SKIP LOCKED) / complete   <- the core
  worker.py   claim -> run handler -> complete
tests/        SQLite unit tests (logic)
bench/        Postgres concurrency demo (SKIP LOCKED)
```

## Build stages

- **Stage 1 — durable queue: enqueue, SKIP LOCKED claim, complete.** ✅ Done. 8 tests,
  `mypy --strict` + `ruff` clean, plus a Postgres demo: **500 jobs / 10 workers ->
  0 duplicates, 0 collisions, work split evenly.**
- **Stage 2 — retries + exponential backoff + dead-letter state.** ✅ Done. A failing
  handler reschedules the job with backoff; after `max_attempts` it is parked `dead`.
- **Stage 3 — lease expiry + crash recovery.** ✅ Done. A leased job whose worker dies
  is reclaimed by another worker once its lease expires (proven by a unit test that
  simulates the crash).
- **Stage 4 — recurring (fixed-interval) schedules + concurrency benchmark.** ✅ Done.
  Completing a recurring job enqueues its next occurrence; the `bench/` demo measures
  throughput. (Full cron-expression parsing is a natural next extension.)

## Run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest                    # logic (SQLite, zero infra)

docker compose up -d db   # Postgres on host port 5434
TICK_DB="postgresql+psycopg://tick:tick@localhost:5434/tick" \
    python bench/skip_locked_demo.py
```

## Stack

Python 3.12, SQLAlchemy 2.0, Pydantic v2. SQLite for local tests; Postgres for the
`SKIP LOCKED` concurrency demo. Typed, tested, CI-ready.
