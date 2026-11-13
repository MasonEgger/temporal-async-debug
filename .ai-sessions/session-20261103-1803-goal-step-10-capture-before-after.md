# Session Summary: Goal Step 10, Capture Before And After

**Date**: 2026-11-03
**Duration**: One autonomous step (live captures, dashboard corrections, finalize)
**Conversation Turns**: Few (dispatch-driven)
**Estimated Cost**: High (live runs of the baseline and five exercises, before and after)
**Model**: Sonnet 5.5 (finalize)

## Goal Context

Step 10 of the `/bpe:goal` run over the regenerated 14-step plan.
The section declares `**Tools:** none`, so no validator ran; the orchestrator reviewed the diff.

## Key Actions

- Captured 53 Grafana PNGs under docs/images/ (about 1.2 MB) for the baseline and each exercise, before and after.
- Corrected the dashboard from the live captures: latency unit is ms, legends, intervals, the server `activity_timeout` series, and a narrowed backlog query.
- Added `activity_timeout` to the metric allowlist in tests/test_observability_config.py.
- Ticked the Step 10 checkboxes in todo.md.
- Final gates: `just check` exit 0 (10 passed), `just check-practice` exit 0 for all practice copies.

## Where The Captures Live

The raw captures are NOT committed (no capture script or dump is a non-goal) and sit in the session scratchpad:

- /tmp/claude-1000/-home-mmegger-Code-MasonEgger-temporal-async-debug/10fd033c-1cfd-409b-a456-989de32d14dd/scratchpad/captures/INDEX.md (maps each file to subject, state, tool, command, timestamp)
- /tmp/claude-1000/-home-mmegger-Code-MasonEgger-temporal-async-debug/10fd033c-1cfd-409b-a456-989de32d14dd/scratchpad/captures/FINDINGS.md

The scratchpad is not durable across sessions, so the findings Steps 11 to 13 need are copied below.
FINDINGS.md was written by the orchestrator from the executor's report because the executor's Write was refused by the harness.
Where FINDINGS.md contradicts spec.md or plan.md prose, FINDINGS.md wins.

## Findings for Steps 11 to 13

### Contradictions list

1. 02: not a retry storm. One Heartbeat timeout; attempt 2 waits Scheduled until the thaw; workflow show text lists no failure. Evidence: describe, the JSON history, the zombie poll lines.
2. 02: the server-side last heartbeat advances about every 4 s, not every second.
3. 03: receipts stall (29.3 s), confirming the plan. GIL contention keeps solution receipts at 79 to 110 ms. A second Worker only helps when runs land on separate processes; one-slot scratch Workers gave about 190 percent combined.
4. 04: the coroutine IS cancelled (about 10 s into each attempt) and the thread runs on. The bad run ends FAILED after three overlapping attempts.
5. 05: the symptom is the first workflow-task gap (298 to 394 ms vs 19 to 23 ms). The debug warning names _ActivityWorker._handle_start_activity_task, not get_location.
6. Dashboard: latency unit was s but the SDK reports ms; worker-side failure metrics never appeared (fixed with the server's activity_timeout); the backlog gauge exists but is almost flat; its label uses underscores.
7. Solution receipts in 01, 02, 03, and 04 wait about 3 s for a slot behind the rollup's pause: slot occupancy, not a freeze.
8. Cause chains: root, 01, and 03 rollups read ScheduleToClose caused by StartToClose; the 04 bad run reads ScheduleToClose caused by Heartbeat.

### Gaps

- 04 solution receipt gaps were not tabulated (workflow show files exist).
- No backlog-panel PNG was taken during a freeze, only the flat baseline one.
