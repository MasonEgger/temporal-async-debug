# Session Summary: Close the Review's Starter, Wiring, and Test Gaps

**Date**: 2026-10-04
**Duration**: One post-review correction pass (implement, three validator iterations, two fix rounds, finalize)
**Conversation Turns**: Orchestrated; one implement dispatch, two fix dispatches, three validator dispatches, one finalize dispatch
**Estimated Cost**: Moderate to high; a large starter rewrite plus history-based workflow tests and three validator passes
**Model**: Implementer Opus 5.5; validator Fable 5.1 (three iterations, clean at iteration 3); finalize Opus 5.5

## Key Actions

- A seven-agent adversarial review of the shipped catalog found four gaps.
  The starter silently dropped the receipts and quotes the block and cpu recipes pass, and the healthy geo the slow recipe passes, so the "instant bystander stalls during a freeze" lesson was never shown.
  The freeze lesson's in-flight guarantee rested on about one second of margin.
  No test checked that the workflows pass heartbeat_timeout and schedule_to_start_timeout through to execute_activity.
  worker.py had zero test coverage of its two deliberate mistunings.
- Starter: added a Fleet/select_scenario seam so every input kind routes somewhere and none can be dropped.
  The freeze path submits receipts and quotes after the bad run.
  The saturation path waits for max(0, baseline - bad) free slots and includes healthy geo runs.
  Every exit path calls os._exit.
- Rollup work raised to 5s to widen the freeze window.
- worker.py: extracted build_worker(client) and flushed the startup banner.
- activities.py: slow_heartbeat heartbeats before every provider attempt; HTTP_TIMEOUT_SECONDS lowered to 4.0 and pinned so 2 x the timeout stays under GEO_HEARTBEAT_TIMEOUT; the IP and location parsers fail over to the next provider on malformed bodies.
- workflow.py: an unknown mode raises ApplicationError(type="InvalidMode") instead of a ValueError that stalled the workflow task forever.
- The maximum_attempts=1 ANTIPATTERN marker now teaches at-most-one dispatch versus exactly-once, with the correct approach being retries plus an idempotent Activity.
- Tests: new tests/history.py helper and history-based assertions for the timeout wiring, new tests/test_worker.py, constant pins, an order-independent regex fixture, and starter ordering tests against a recording fake client.
  74 tests became 117; `just check` is green.

## Deviations from Plan

- Plan said: heartbeat once, guarded by activity.in_activity(), immediately before the provider HTTP phase in get_ip/get_location when mode is slow_heartbeat.
- Deviated: heartbeat before every provider attempt (helper `_heartbeat_before_provider_attempt`), since _apply_mode's loop already heartbeats right before HTTP and a single pre-phase heartbeat cannot cover failover across several providers.
- Impact: each attempt starts with a fresh heartbeat. The residual risk (HTTP_TIMEOUT_SECONDS equal to the heartbeat timeout) was closed later in the pass, below.
- Deviated: the freeze path skips the slot wait when there are no rollups or healthy geo runs to occupy a slot, instead of burning the 20s poll timeout.
- Impact: none for the shipped justfile recipes, which always include early bystanders.
- Plan said: the maximum_attempts=1 marker read "disables retries so the demo surfaces the first failure"; HTTP_TIMEOUT_SECONDS was 10.0.
- Deviated: rewrote the marker to teach at-most-one dispatch vs. exactly-once (Correct: keep retries, idempotent Activity keyed on workflow_run_id plus activity_id) and updated the GeoEnrichmentWorkflow class docstring to match. Lowered HTTP_TIMEOUT_SECONDS to 4.0 and pinned HTTP_TIMEOUT_SECONDS < GEO_HEARTBEAT_TIMEOUT in tests/test_geo_options.py.
- Impact: per-phase connect plus read is at most 8s, under 10s; no existing test or respx mock depended on 10s. Marker count in src/ is still 6.
- Plan said: validator iteration 1 fixes apply the two warn findings and residual edges A and B.
- Deviated: GeoEnrichmentWorkflow raises ApplicationError(type="InvalidMode") without non_retryable; the test asserts the type and the "unknown mode" message. Added a 2 x HTTP_TIMEOUT_SECONDS < GEO_HEARTBEAT_TIMEOUT pin. The freeze path clamps its wait target with max(0, baseline_free - 1) and warns when baseline_free is 0. New tests cover baseline 0 and a fleet with only receipts and quotes.
- Impact: 117 tests, `just check` green.
- Plan said: validator iteration 2 fixes reword the stale "non-retryable" docstring in tests/test_workflow.py and remove the 5s wall-clock cost from the rollup happy-path workflow test.
- Deviated: the unknown-mode test docstring now says the run fails with an ApplicationError of type InvalidMode. tests/test_rollup.py has one module-level roll_up_sales_stub shared by the happy-path and concurrent workflow tests; the ActivityEnvironment test with work_seconds=0.0 still covers the real activity.
- Impact: the rollup happy-path test no longer sleeps 5s; test count unchanged.

## Efficiency Insights

**What went well:**
- The Fleet/select_scenario seam turned "no input kind is dropped" into a property the tests can check directly, instead of a per-recipe audit.
- Reading the recorded workflow history proved the timeout wiring without a running server.

**What could improve:**
- Two fix rounds were spent on edges (baseline 0, receipts-only fleet, stale docstring) that a closer pass over the review findings could have caught in implement.

**Course corrections:**
- The first InvalidMode fix set non_retryable on a Workflow-raised ApplicationError; the validator flagged it as meaningless there and it was dropped.

## Process Improvements

- When a review finding concerns timing margin, pin the margin as a test inequality (here 2 x HTTP_TIMEOUT_SECONDS < GEO_HEARTBEAT_TIMEOUT) so a later constant change cannot silently reopen it.

## Observations

- README.md, CLAUDE.md, spec.md, plan.md, todo.md, and the justfile were left to other streams and not committed here.

## Suggested Skills for Next Session

- `temporal:temporal-developer`: any follow-up to the retry, heartbeat, or timeout wiring.
- `python:python`: further starter or test work under strict mypy.
- `content-design:tutorial-writing`: the README stream needs to reflect the starter's new submission order and the reworded maximum_attempts lesson.
