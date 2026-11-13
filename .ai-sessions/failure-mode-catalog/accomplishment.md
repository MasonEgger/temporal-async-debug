# Accomplishment: Failure-Mode Catalog

**Archived**: 2026-11-01
**Convergence**: converged (78 of 78 todo sub-steps checked)

## Spec Slice

This plan built the full failure-mode catalog on top of the two-workflow foundation (GeoEnrichmentWorkflow, OrderReceiptWorkflow).
The target: one worker runs four unrelated workflow types on a single asyncio event loop with two activity slots, and a `--mode` input drives the geo activities into five misbehaviors.
Three diagnostic stories had to come out of the tooling alone.
A frozen loop (`block`, `cpu`) dead-ends one activity task at the SDK handler while the rest park at awaits, separated by CPU (near zero for `block`, 100 percent for `cpu`) and named to the line by `py-spy`.
A saturated worker (`slow`, `slow_heartbeat`) parks every task at a healthy await with zero free slots and a climbing task-queue backlog.
A heartbeat loss (`stuck_no_heartbeat`) fails fast under a `heartbeat_timeout` it never satisfies.
Every activity timeout had to be shown firing (`start_to_close`, `schedule_to_close`, `schedule_to_start`, `heartbeat`), the cross-type blast radius had to be real (the in-flight rollup fails when the geo loop freezes), and every deliberate bug had to carry the greppable antipattern marker.

## What Got Done

- Added the `cpu`, `slow_heartbeat`, and `stuck_no_heartbeat` modes to `_apply_mode`, with markers on the CPU busy loop and the missing-heartbeat branch and none on the correct `slow_heartbeat`.
- Extended the event-loop starvation probe to prove `block` and `cpu` starve a 50 ms ticker while `slow` and `slow_heartbeat` do not.
- Added `SalesRollupWorkflow` (short-work bystander caught in-flight by a freeze) and `PriceQuoteWorkflow` (the one `schedule_to_start_timeout` sample, marked).
- Centralized per-mode geo activity options in `geo_activity_options(mode)`: generous `start_to_close`, `heartbeat_timeout` for the two heartbeating modes, `maximum_attempts=1` marked throughout.
- Registered all four workflow types and every activity on the worker, keeping `max_concurrent_activities=2` (marked) and the Prometheus endpoint on 127.0.0.1:9464.
- Extended the starter to the full five-mode scenario set with the deterministic freeze ordering (gate on `get_location` STARTED plus a 1-second guard) and the saturation ordering.
- Added one `just` recipe per scenario and rewrote the README as the two-tool catalog tutorial with captured output.
- Corrected the frozen-loop diagnostic signature, the spec, and CLAUDE.md to the live-measured October 2026 behavior across a seven-pass adversarial review.

## Notable Decisions

- The frozen-loop signature was corrected mid-arc to the two-tool story: `asyncio ps` and `pstree` show the frozen-loop shape and which task is wedged, but not the blocking line, because a task stuck in synchronous code is not suspended at an await; `py-spy dump` names the line. The earlier claim that `asyncio ps` shows the line was wrong and was removed from every document.
- The freeze-path bystander gate moved from the first freezing activity (`get_ip`) to the second (`get_location`) plus a 1-second guard, after a bystander released into the sub-second thaw between the two freezes raced the re-freeze and failed `ScheduleToClose` once in 16 live runs.
- `maximum_attempts=1` is set only on the geo activities; receipt, rollup, and quote keep the default retry policy, because the frozen-loop rollup failure chain depends on that default's second attempt.

## Files Touched

- `src/temporal_async_debug/`: `shared.py`, `activities.py`, `workflow.py`, `rollup.py`, `quote.py`, `worker.py`, `starter.py`
- `tests/`: the activity, starvation-probe, rollup, quote, geo-options, worker, starter, and history-based timeout tests
- `justfile`, `README.md`, `CLAUDE.md`
- `.github/workflows/ci.yml` (action bumps, pip-audit)
- `docs/drafts/` (original draft imported as provenance)

## Lessons Cross-Reference

- Capture real tool output before writing prose; do not invent `asyncio ps`, `py-spy`, or metrics output (lessons.md, Testing).
- Guard `activity.heartbeat` with `activity.in_activity()` in code reused outside an activity, so the starvation probe can call `_apply_mode` without a worker (lessons.md).
- Prefer wide-slack thresholds in timing-sensitive probe tests in one pass, rather than tightening after a flake (lessons.md, Testing).
- Keep the `default` (`@just --list`) recipe first in the justfile so bare `just` prints help (lessons.md, Workflow).
