# Accomplishment: Event-Loop Exercises

**Archived**: 2026-11-10
**Convergence**: converged (165 of 165 todo items checked)

## Spec Slice

This plan implemented the `event-loop-exercises` arc of `spec.md`.
The November 2, 2026 rescope narrowed the whole repository to one mechanism: a blocking call in an `async def` Activity freezes the Worker's shared asyncio event loop.
The arc trimmed the root failure-mode catalog down to the frozen-loop reference (modes `block` and `cpu`), dropping the saturation, heartbeat, schedule-to-start, and retry-policy material.
It then built five exercises in the practice and solution shape, each with a failure visible in the execution, the Python tools that find the blocker, a fix the reader applies, and tests that cover invariants only.
A Prometheus and Grafana stack shows what a frozen loop does to the Worker over time.
Every figure and every block of tool output in the prose had to come from a real capture.
The arc closed with the five exercise READMEs, the root README and CLAUDE.md refresh, and a six-part tutorial series in `docs/drafts/`.
A review on November 5, 2026 added a rework pass (Steps 14 to 22) on exercises 02, 03, and 05, the receipt-gap helper, and the prose that quotes them.

## What Got Done

- Added the Vale config, the prose lint recipes, and the `just preflight` gate.
- Trimmed the root package to the frozen-loop reference: `block` and `cpu` only, three Workflow types, two antipattern markers.
- Added the observability stack (`observability/docker-compose.yml`, `prometheus.yml`, the provisioned six-panel dashboard) with its config tests, and the `just server`, `just metrics`, and `just metrics-down` recipes.
- Added the per-directory gate: `just check` loops over `exercises/*/solution`, and `just check-practice` runs ruff and mypy on each practice copy.
- Built exercise 01 (a synchronous HTTP client), 02 (a sleep between heartbeats), 03 (a CPU-bound transform), 04 (a zombie thread behind an `async def` Activity), and 05 (a probe test that catches a loop blocker before it ships).
- Captured before-and-after tool output and Grafana panels for every exercise and for the root baseline.
- Wrote the five exercise READMEs, the six series drafts, and the refreshed root README, CLAUDE.md, and `docs/drafts/README.md`.
- Rework: rebuilt exercise 02 so the Heartbeat timeout shows as a climbing Attempt count, gave exercise 05 a generated audit trail in place of random bytes, added `ASYNC_DEBUG_METRICS_PORT` to exercise 03's Worker, committed `scripts/receipt_gaps.py` with its tests, recaptured, and updated every document that quotes the changed runs.

## Deferred or Dropped

- A committed capture script that reproduces whole before-and-after runs stays deferred; only the read-only receipt-gap helper shipped.
- Exercise 04's forced-timeout demo stays a described extension the reader edits in by hand.
- The copy-editor pass on the reworked prose never ran.
- Eleven smaller open questions from the review (panel recaptures, a Heartbeat series on the failures panel, primer numbering, and others) carry into the next phase, where the builder decides each one and lists the choices for the owner.

## Notable Decisions

- A retried Activity writes no history event per attempt, so `temporal workflow show` cannot show exercise 02's storm.
  The exercise shows it in the Web UI's pending-activity view, in `temporal workflow describe`, and in the Worker log; exercise 02 is the one place Web UI screenshots are allowed.
- Exercise 02 leads with the climbing Attempt count and names `TMPRL1101` as a log line the reader will probably see, with a note that it depends on timing.
- Exercise 05 keeps `zlib.compress` because it releases the GIL, so the `asyncio.to_thread` fix visibly restores receipt latency; a pure-Python blocker kept receipts slow after the fix through GIL contention.
- The root gate excludes `exercises/`, because every copy reuses the same flat module names; each copy is checked from inside its own directory.
- A `solution/` copy carries no antipattern and no marker, so the marker search finds the root package and the practice copies only.
- `temporal task-queue describe` is the reliable backlog reading; the dev server's backlog gauge is nearly flat and the dashboard only corroborates.
- Where captured output disagrees with `spec.md` or the plan, the captures win.

## Files Touched

- `src/temporal_async_debug/` and `tests/` (the trim)
- `exercises/01-sync-http-client/` to `exercises/05-catching-blockers-early/`, each with `README.md`, `practice/`, and `solution/`
- `scripts/receipt_gaps.py` and its tests
- `observability/` (`docker-compose.yml`, `prometheus.yml`, `grafana/`)
- `docs/drafts/` (six parts, `README.md`, `smell-reports.md`) and `docs/images/`
- `justfile`, `.vale.ini`, `README.md`, `CLAUDE.md`, `spec.md`

## Lessons Cross-Reference

- Capture real tool output before writing prose, and diff every figure against the raw output before committing it (lessons.md, Testing and Workflow).
- A retried Activity writes no history event per attempt; read the Attempt count from `describe` or the Web UI (lessons.md, Temporal).
- A blocker that holds the GIL keeps bystanders slow even after it moves to a thread; pick a blocker that releases the GIL when the fix must show in the latency (lessons.md, Temporal).
- pytest resolves a relative `pythonpath` against the config file's directory, not the current directory, so the per-directory gate passes an absolute path (lessons.md, Testing).
