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

Demo-running recipes (require `temporal server start-dev` and the worker running in separate terminals):

```bash
just server              # local Temporal dev server
just worker               # the demo worker (prints its PID for asyncio introspection)
just trigger name="x"     # a healthy, non-blocking workflow run
just block seconds="30"   # frozen-event-loop lesson (time.sleep blocks the worker)
just slow seconds="30"    # slot-exhaustion lesson (cooperative but hogs both activity slots)
```

## Architecture

Package lives under `src/temporal_async_debug/` (src layout, hatchling build backend, Python 3.14+ required).
Per `spec.md`, the modules are:

- `shared.py`: frozen dataclasses for workflow inputs/outputs and the task queue name constant.
- `activities.py`: the misbehaving workflow's two async activities (`get_ip`, `get_location`, httpx-based). Each heartbeats, then branches on a `mode` field: `"block"` calls `time.sleep` (the deliberate bug, freezes the worker's single asyncio event loop), `"slow"` awaits `asyncio.sleep` (cooperative, but still occupies an activity slot).
- `victim.py`: `VictimWorkflow`, an innocent, correct-in-every-respect workflow used to demonstrate collateral damage from the misbehaving workflow's failure modes.
- `workflow.py`: `GreetingWorkflow`, the misbehaving workflow, orchestrating `get_ip` then `get_location`.
- `worker.py`: connects to the Temporal server, registers both workflows and all activities, and is deliberately mistuned (`max_concurrent_activities=2`) to make slot exhaustion reproducible. Exposes Prometheus metrics on `localhost:9464`. Prints a startup banner with its PID and copy-paste `python -m asyncio ps`/`pstree` commands.
- `starter.py`: CLI (argparse) for submitting workflow runs with configurable mode, block duration, and concurrency.

The core teaching mechanism: the Temporal Python worker runs its poller, heartbeat sender, and every `async def` activity on **one** asyncio event loop.
A single blocking call (the `time.sleep` antipattern) starves all of them at once; this is diagnosable from outside the process with Python 3.14's native `asyncio ps`/`pstree` introspection, with zero instrumentation.
A separate failure mode, exhausting the worker's `max_concurrent_activities` slots, looks similar to a downstream workflow (it stalls) but has a different signature in the tooling (healthy stacks, metrics show zero available slots) and a different fix (resize the worker, don't touch the event loop).
`spec.md`'s Behavior Requirements section spells out exactly what each mode must produce.

Tests must never require a running Temporal server except through the SDK's own test facilities (`temporalio.testing.ActivityEnvironment`, `WorkflowEnvironment.start_time_skipping()`); all network calls are mocked.
