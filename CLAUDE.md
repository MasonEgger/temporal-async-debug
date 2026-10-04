# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A deliberately misbehaving Temporal Python demo, built as a teaching companion to a tutorial on diagnosing blocking calls in `async def` activities.
Every intentional bug or mistuning is a feature of the demo, not a defect: it must be preserved and must carry the marker comment described below.
Do not "fix" antipatterns you find here unless the task explicitly asks you to change the demo's behavior.

The build is driven by `spec.md` (requirements) and `plan.md`/`todo.md` (the step-by-step execution plan, consumed by `/bpe:execute-plan` or `/bpe:goal`).
Read `spec.md` in full before making architectural decisions; it is the source of truth for behavior this repo must exhibit.

## Antipattern marker convention

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

## Architecture

Package lives under `src/temporal_async_debug/` (src layout, hatchling build backend, Python 3.14+ required).
The modules are:

- `shared.py`: frozen dataclasses for every workflow's input and output, `VALID_MODES` (`block`, `cpu`, `slow`, `slow_heartbeat`, `stuck_no_heartbeat`), and the task queue name constant.
- `activities.py`: `get_ip` and `get_location` (httpx-based). Both call `_apply_mode`, which branches on the five modes. `block` calls `time.sleep` and `cpu` spins in a busy loop (both freeze the loop). `slow` awaits `asyncio.sleep`. `slow_heartbeat` awaits in steps and heartbeats correctly. `stuck_no_heartbeat` awaits one long sleep and never heartbeats. The `block` line, the `cpu` loop, and `stuck_no_heartbeat` carry markers. `slow_heartbeat` is correct and has none.
- `workflow.py`: `GeoEnrichmentWorkflow`, the workflow that carries the bad modes, and `geo_activity_options`, which picks per-mode timeouts. It sets `maximum_attempts=1` (marked).
- `receipt.py`: `OrderReceiptWorkflow`, an instant in-memory bystander.
- `rollup.py`: `SalesRollupWorkflow`, a short-work bystander (a two-second cooperative pause, then a sum).
- `quote.py`: `PriceQuoteWorkflow`, the schedule-to-start sample. It is the one place a `schedule_to_start_timeout` is set (marked).
- `worker.py`: registers all four workflow types and all activities on one task queue, with `max_concurrent_activities=2` (marked) so slot exhaustion is reproducible. Exposes Prometheus metrics on `localhost:9464`. Prints a startup banner with its PID and copy-paste `python -m asyncio ps`/`pstree` commands.
- `starter.py`: fleet CLI (argparse) over the five modes, with `--bad`, `--geo`, `--rollups`, `--receipts`, `--quotes`, and `--block-seconds`. It orders submissions so the freeze or saturation is in place before the bystanders arrive, and exits with `os._exit(0)`.

The core teaching mechanism: the Temporal Python worker runs its pollers, heartbeat sender, workflow task processing, and every `async def` activity on **one** asyncio event loop.
The four workflow types are unrelated, yet they share that loop and the same two activity slots.
A misbehaving geo activity therefore fails the rollups, receipts, and quotes too, even though their code is correct (the cross-type blast radius).

The two root causes look alike from a workflow's point of view and differ in the tooling:

- Frozen loop (`block`, `cpu`): a single blocking or CPU-bound call starves everything at once.
  `python -m asyncio ps` and `pstree` show the shape with zero instrumentation: the wedged task dead-ends at the SDK handler `_ActivityWorker._handle_start_activity_task` with no await beneath it, and the other tasks sit parked at awaits.
  They do not name the blocking line, because a task stuck in synchronous code is not suspended at an await.
  `py-spy dump` reads the OS thread stack and names the exact line.
  CPU separates the two causes: near zero for `block` (`time.sleep` releases the GIL), 100 percent for `cpu`.
  The metrics endpoint stays reachable during a freeze, so it is not a freeze signal.
- Saturated worker (`slow`, `slow_heartbeat`): the loop is healthy but every activity slot is full.
  Every task is parked at an await with a complete stack, `temporal_worker_task_slots_available` reads 0, the task-queue backlog age in `temporal task-queue describe` keeps climbing, and the poller `LastAccessTime` goes stale.
  The fix is to resize the worker, not to touch the event loop.
- Heartbeat loss (`stuck_no_heartbeat`): the loop is healthy and one slot is held without heartbeats, so the heartbeat timeout fails the run fast.

`spec.md`'s Behavior Requirements section spells out exactly what each mode must produce, and `README.md` is the tutorial companion with captured output for each lesson.

Tests must never require a running Temporal server except through the SDK's own test facilities (`temporalio.testing.ActivityEnvironment`, `WorkflowEnvironment.start_time_skipping()`); all network calls are mocked.
