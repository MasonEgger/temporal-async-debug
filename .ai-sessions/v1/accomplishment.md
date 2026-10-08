# Accomplishment: The Two-Lesson Greeting/Victim Demo

**Archived**: 2026-09-21
**Convergence**: converged (86 of 86 items checked), then substantially superseded by the two-workflow redesign

## Spec Slice

This plan implemented the original, narrower spec: a single misbehaving `GreetingWorkflow`
(get_ip then get_location) plus an innocent `VictimWorkflow`, on one deliberately
mistuned worker, teaching two lessons: a frozen event loop (the `time.sleep`
antipattern) and slot exhaustion (`max_concurrent_activities=2`). Diagnosis was from
Python 3.14 `asyncio ps` / `pstree` plus the SDK Prometheus metrics, with the
antipattern-marker convention applied to every deliberate bug.

The spec has since grown well past this slice into the full failure-mode catalog
(see the current spec.md); this archive records the first working build that the
catalog is built on top of.

## What Got Done

- Scaffolded the package and test tree (b142c8b) and shared payloads plus the task queue constant (45abde1).
- Built the misbehaving activities with block/slow mode logic and the `time.sleep` antipattern marker (91d3f40).
- Proved the event-loop freeze deterministically without a Temporal server via the starvation probe test (4a7ef09).
- Added the misbehaving `GreetingWorkflow` (a1f9e02) and the innocent `VictimWorkflow` (c17316d), stabilizing the concurrent victim test (c07c16e).
- Added the deliberately mistuned worker with metrics and PID banner (86b84a0) and the starter CLI (a69e6c9).
- Wrote the README diagnostic guide and MIT license (f5e6f67) and CI plus dependency automation (6f54231).

## Deferred or Dropped

- The heartbeat-based `heartbeat_timeout` demonstration and the `schedule_to_start_timeout` on the victim were later reconsidered; heartbeats were dropped from the redesign as making the failure too easy to spot.

## Notable Decisions

- Labeled roles (`GreetingWorkflow` culprit, `VictimWorkflow` victim) were the original framing; the redesign replaced them with two neutrally-named workflow types (GeoEnrichment, OrderReceipt) so the reader diagnoses from the tooling, not from names.
- The single blocking-vs-cooperative contrast was proven in CI with a Temporal-free starvation probe; live signatures were left to the tutorial. Both choices carried forward into the catalog.

## Files Touched

- src/temporal_async_debug/: shared.py, activities.py, workflow.py, victim.py (later deleted), worker.py, starter.py, __init__.py, py.typed
- tests/: test_shared.py, test_activities.py, test_starvation_probe.py, test_workflow.py, test_victim.py (later deleted), test_starter.py, test_package.py, conftest.py
- README.md, LICENSE, pyproject.toml, justfile, .github/workflows/ci.yml, .github/dependabot.yml

## Lessons Cross-Reference

- "pytest exits 5 when it collects no tests ... give a freshly scaffolded package a single import smoke test" (2026-09-17)
- "An error-path test that asserts only the exception type does not prove a retry policy is disabled ... assert the attempt count" (2026-09-17)
- "For timing-based probe tests, pick gap thresholds with wide slack in one pass" (2026-09-17)
- "schedule_to_start_timeout combined with WorkflowEnvironment.start_time_skipping is flaky ... test under start_local" (2026-09-17)
