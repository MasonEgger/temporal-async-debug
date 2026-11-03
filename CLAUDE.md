# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A deliberately misbehaving Temporal Python demo, built as a teaching companion to a tutorial on diagnosing blocking calls in `async def` activities.
Every intentional bug or mistuning is a feature of the demo, not a defect: it must be preserved and must carry the marker comment described below.
Do not "fix" antipatterns you find here unless the task explicitly asks you to change the demo's behavior.

The build is driven by `spec.md` (requirements) and `plan.md`/`todo.md` (the step-by-step execution plan, consumed by `/bpe:execute-plan` or `/bpe:goal`).
Read `spec.md` in full before making architectural decisions; it is the source of truth for behavior this repo must exhibit.

The current plan is the `event-loop-exercises` arc: it trims this package to the frozen-loop reference (`block` and `cpu` only), then adds five `exercises/` in the Temporal 102 `practice/` and `solution/` layout, an `observability/` Prometheus and Grafana stack, and a six-part tutorial draft.
The whole arc is about one mechanism, blocking the shared asyncio event loop; the spec's Invariants forbid any slot-exhaustion, heartbeat-tuning, timeout-tuning, or retry-policy lesson.
The Architecture and Commands sections below describe the package at HEAD, which is the shipped failure-mode catalog (its plan is archived under `.ai-sessions/failure-mode-catalog/`); plan.md's Step 13 refreshes them once the trim and the exercises land.

## Antipattern Marker Convention

Every deliberately wrong line, setting, or pattern carries a comment of this exact, greppable form on or immediately above the offending line:

```
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```

Find them all with `grep -rn "ANTIPATTERN (deliberate, for teaching)"`.
Any new deliberate bug or mistuning added to this repo must carry this marker; a validator pass will flag one that doesn't.

## Commands

Toolchain is `uv` + `ruff` + `mypy` (strict) + `pytest`, orchestrated through `just`:

```bash
just check   # full gate: ruff check, ruff format --check, mypy strict, pytest
just fmt     # ruff format + ruff check --fix
just test    # pytest only
```

Run a single test with `uv run pytest path/to/test_file.py::test_name`.

Demo-running recipes (require `temporal server start-dev` and the worker running in separate terminals; the scenario recipes take an optional `seconds` argument, default 30):

```bash
just server                # local Temporal dev server
just worker                # the demo worker (prints its PID for asyncio introspection)
just healthy               # full healthy fleet (geo, rollup, receipt, quote), all completing
just trigger               # smaller healthy fleet (geo and receipts only), a quick smoke test
just block seconds="30"    # frozen-loop lesson (time.sleep blocks the worker)
just cpu seconds="30"      # frozen-loop lesson, CPU-pinned (busy loop holds the GIL)
just slow seconds="30"     # slot-exhaustion lesson (asyncio.sleep hogs both activity slots)
just slow-heartbeat seconds="30"  # slot exhaustion with a correct, heartbeating activity
just stuck seconds="30"    # heartbeat-loss lesson (no heartbeat, trips heartbeat_timeout)
```

`just stuck` follows the saturation ordering in the starter: it waits for the bad run to take its slot before submitting the bystanders.

## Architecture

Package lives under `src/temporal_async_debug/` (src layout, hatchling build backend, Python 3.14+ required).
The modules are:

- `shared.py`: frozen dataclasses for every workflow's input and output, `VALID_MODES` (`block`, `cpu`, `slow`, `slow_heartbeat`, `stuck_no_heartbeat`), and the task queue name constant.
- `activities.py`: `get_ip` and `get_location` (httpx-based, `HTTP_TIMEOUT_SECONDS` of 4.0).
  Both call `_apply_mode`, which branches on the five modes.
  `block` calls `time.sleep` and `cpu` spins in a busy loop (both freeze the loop).
  `slow` awaits `asyncio.sleep`.
  `slow_heartbeat` awaits in steps and heartbeats correctly.
  `stuck_no_heartbeat` awaits one long sleep and never heartbeats.
  The `block` line, the `cpu` loop, and `stuck_no_heartbeat` carry markers.
  `slow_heartbeat` is correct and has none.
- `workflow.py`: `GeoEnrichmentWorkflow`, the workflow that carries the bad modes, and `geo_activity_options`, which picks the per-mode heartbeat_timeout (start_to_close and schedule_to_close are the same for every mode).
  It sets `maximum_attempts=1` (marked) and raises `ApplicationError(type="InvalidMode")` on an unknown mode.
  `maximum_attempts=1` is set only on the geo activities; receipt, rollup, and quote keep the default retry policy.
  It is an antipattern because one attempt gives at-most-one dispatch, not exactly-once; effectively-once comes from keeping retries plus an idempotent Activity keyed on `workflow_run_id` and `activity_id`.
- `receipt.py`: `OrderReceiptWorkflow`, an instant in-memory bystander.
- `rollup.py`: `SalesRollupWorkflow`, a short-work bystander (a five-second cooperative pause, then a sum).
- `quote.py`: `PriceQuoteWorkflow`, the schedule-to-start sample.
  It is the one place a `schedule_to_start_timeout` is set (marked).
- `worker.py`: `build_worker(client)` registers all four workflow types and all activities on one task queue, with `max_concurrent_activities=2` (marked) so slot exhaustion is reproducible.
  Exposes Prometheus metrics on `localhost:9464`.
  Prints a startup banner with its PID and copy-paste `python -m asyncio ps`/`pstree` commands.
- `starter.py`: fleet CLI (argparse) over the five modes, with `--bad`, `--geo`, `--rollups`, `--receipts`, `--quotes`, and `--block-seconds`.
  `fleet_from_args` builds a `Fleet`, and `select_scenario` routes it to the freeze, saturation, or concurrent ordering; no bystander kind is dropped.
  The freeze path puts rollups in flight and awaits the healthy geo before submitting the bad run.
  It then waits until the server reports the bad run's second activity (`get_location`) STARTED, plus a 1-second guard, before submitting receipts and quotes, so they stall through the final freeze and complete at the thaw.
  The geo workflow freezes twice (`get_ip`, then `get_location`) with a fraction of a second of live loop between (60 to 570 ms across the 8 final runs, depending on `get_ip`'s HTTP call; 138 ms in the run that exposed the race), and a bystander released into that gap can be dispatched just as the loop re-freezes and time out, which is why the gate waits on the second activity.
  The saturation path waits for the bad runs to hold their slots first.
  It exits with `os._exit(0)`.

The core teaching mechanism: every `async def` activity, the Python side of workflow task handling, heartbeat recording, and the Python tasks that hand poll results to user code share **one** asyncio event loop, so a single blocking call freezes them together.
The Rust core's network polling and the Prometheus endpoint run on their own threads and keep going, which is why the server keeps dispatching tasks that then time out and why the metrics endpoint still answers during a freeze.
The four workflow types are unrelated, yet they share that loop and the same two activity slots.
A misbehaving geo activity therefore fails the rollups, receipts, and quotes too, even though their code is correct (the cross-type blast radius).

The two root causes look alike from a workflow's point of view and differ in the tooling:

- Frozen loop (`block`, `cpu`): a single blocking or CPU-bound call starves everything on the loop at once.
  `python -m asyncio ps` and `pstree` show the shape with zero instrumentation: the wedged task dead-ends at the SDK handler `_ActivityWorker._handle_start_activity_task` with no await beneath it, and the other tasks sit parked at awaits.
  They do not name the blocking line, because a task stuck in synchronous code is not suspended at an await.
  `py-spy dump` reads the OS thread stack and names the exact line.
  CPU separates the two causes: near zero for `block` (`time.sleep` releases the GIL), 100 percent for `cpu`.
  The in-flight rollup fails `ScheduleToClose` caused by `StartToClose`; receipts and quotes stall and complete at the thaw, about 29 seconds after submission.
  The metrics endpoint stays reachable during a freeze, answering in a few milliseconds, so it is not a freeze signal.
  `temporal_worker_task_slots_available` reads 0 whenever both slots are held, in either family, so slots alone do not discriminate.
  The pollers live in the Rust core and keep long-polling through a freeze, so poller `LastAccessTime` is not a freeze signal either.
- Saturated worker (`slow`, `slow_heartbeat`): the loop is healthy but every activity slot is full.
  Every task is parked at an await with a complete stack, and `temporal_worker_task_slots_available` reads 0.
  The tell is the task-queue backlog age in `temporal task-queue describe`, which keeps climbing, read together with that healthy `asyncio ps` shape.
  A freeze also shows a backlog while no permit is free (the rollup's retry, 8.9 seconds old at t+20 of a `block` run), so a backlog under a dead-ended task is the freeze.
  The activity poller's `LastAccessTime` grows only while no activity permit is free, and idle values already cycle up to about 59 seconds, so it is at most a weak hint.
  The starved receipts, rollup, and quote fail with the `ScheduleToStart` label, even the ones that only set `schedule_to_close`.
  The healthy geo queues behind the hold and completes late (about 60 seconds), because its `schedule_to_close` is 150 seconds.
  `temporal_activity_schedule_to_start_latency` records only when a queued task starts, so it is a lagging confirmation.
  The fix is to resize the worker, not to touch the event loop.
- Heartbeat loss (`stuck_no_heartbeat`): the loop is healthy and one slot is held without heartbeats, so the heartbeat timeout fails the run fast.

`spec.md`'s Behavior Requirements section spells out exactly what each mode must produce, and `README.md` is the tutorial companion with captured output for each lesson.

Tests must never require a running Temporal server except through the SDK's own test facilities (`temporalio.testing.ActivityEnvironment`, `WorkflowEnvironment.start_time_skipping()`); all network calls are mocked.
