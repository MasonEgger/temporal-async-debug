# Session Summary: Goal Step 6, Exercise 02 Sleep Between Heartbeats

**Date**: 2026-11-03
**Duration**: One autonomous step (implement, validate, one fix pass, finalize)
**Conversation Turns**: Few (dispatch-driven)
**Estimated Cost**: Moderate
**Model**: Sonnet 5.5 (finalize)

## Goal Context

Step 6 of the `/bpe:goal` run over the regenerated 14-step plan.
Creates exercises/02-sleep-between-heartbeats/ with a solution/ and a practice/ copy.

## Key Actions

- Built the solution copy: a poll loop over a slow job that waits in awaited 1-second ticks and heartbeats on each tick.
- Built the practice copy: one heartbeat, then a single `time.sleep(poll_interval)` per poll, marker kept, with `# TODO PART C` and `# TODO PART D`.
- Ticked the Step 6 checkboxes in `todo.md`.
- `just check` and `just check-practice` both exit 0.
- Validated clean at iteration 2 after one fix pass.

## As-Built Design

- `async def get_location(ip, slow_job)`.
- `get_ip` and `get_location` use `httpx.AsyncClient`, so the deliberate `time.sleep` is the only thing that blocks the loop.
  This differs from exercise 01, where the sync HTTP client is the bug.
  The Step 11 README should say so.
- There is no `slow_upstream.py` and no `--block-seconds`.
- Fixed scenery: `JOB_SECONDS` 20, `POLL_INTERVAL_SECONDS` 8, `TICK_SECONDS` 1, `GEO_HEARTBEAT_TIMEOUT` 5 s.
- Job state is keyed on the workflow id and the run id.
- Default retry policy.
- Poll lines are printed with `flush=True`; they are the zombie evidence.
- The test monkeypatches the timings so one poll wait spans several ticks.

## Deviations from Plan (Findings for Step 10)

This contradicts the prose in spec.md (Architecture 02, Exercise requirements 02) and plan.md (Architecture Recap row 02, Step 6 note), which describe a multi-attempt "retry storm".

- The implement dispatch's live smoke of practice/ showed ONE Heartbeat-timeout attempt.
- The zombie attempt printed poll lines at 8, 16, and 24 s after the server had already failed it.
- Attempt 2 started only at about 24 s, when the zombie thawed the loop, and completed at once because the job was done.
- Why: the practice loop never awaits between polls, so the loop stays frozen until the job is done, and the retry cannot run any Python before then.
- The validator confirmed the code is correct for the decided design.
- Step 10 must capture the real shape, including whether the server also times out attempt 2 before Python reaches it.
- Steps 11 and 12 must describe what the capture shows, not "retry storm".
- The solution smoke completed on attempt 1 in about 24 s with no heartbeat timeout.
- The rollup failed in practice (cross-type blast radius) and completed in solution.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Mode: implement, Step 6 | Created both exercise copies, live smoke | Tests green, smoke exposed the zombie shape |
| Mode: fix, iteration 1 | Applied validator findings | Validated clean at iteration 2 |
| Mode: finalize, Step 6 | Ran both gates, wrote this summary and a lesson, committed and pushed | See commit |

## Observations

- `git status --porcelain --untracked-files=all exercises/` lists only source and test files, no caches.
- Info finding left as-is: the `_JOB_STARTED_AT` docstring and `_job_is_done`'s run_id arg say "workflow run id" but the key is `workflow_id/run_id`; kept to minimize the practice-to-solution diff.
