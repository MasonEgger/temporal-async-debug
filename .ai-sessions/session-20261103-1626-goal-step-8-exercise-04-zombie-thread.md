# Session Summary: Goal Step 8, Exercise 04 Zombie Thread

**Date**: 2026-11-03
**Duration**: One autonomous step (implement, validate, one fix pass, finalize)
**Conversation Turns**: Few (dispatch-driven)
**Estimated Cost**: Moderate
**Model**: Sonnet 5.5 (finalize)

## Goal Context

Step 8 of the `/bpe:goal` run over the regenerated 14-step plan.
Creates exercises/04-zombie-thread/ with a solution/ and a practice/ copy.

## Key Actions

- Built the solution copy: `def get_location` on `httpx.Client`, heartbeating once per step from its own thread.
- Built the practice copy: `async def get_location` on `httpx.AsyncClient` awaiting `asyncio.to_thread`, no heartbeat, marker kept, `# TODO PART C` and `# TODO PART D`.
- Ticked the Step 8 checkboxes in `todo.md`.
- `just check` and `just check-practice` both exit 0.
- Validated clean at iteration 2 after one fix pass.

## As-Built Design

- The work is `_blocking_work(location, steps, attempt)` with `STEP_SECONDS` 0.5 and `BAD_WORK_STEPS` 20 (a 10 s job).
  It prints a progress line per step with `flush=True`.
- Practice `get_location` is `async def` on `AsyncClient` and awaits `asyncio.to_thread`, with no heartbeat.
- Solution `get_location` is a plain `def` on `httpx.Client`.
  It heartbeats per step from its own thread, and catches `temporalio.exceptions.CancelledError` only to print and re-raise.
  There is no separate heartbeat thread.
- `get_ip` is `async def` in both copies, per the Step 7 ruling.
- `heartbeat_timeout` is 5 s on `get_location`.
- `GEO_START_TO_CLOSE` and `GEO_SCHEDULE_TO_CLOSE` are both 20 s in this copy.
  This is accepted scenery: it bounds the bad run to about 3 attempts under the default retry policy.
- `ActivityEnvironment` was confirmed from the installed `temporalio/testing/_activity.py` to raise `CancelledError` into a sync activity's thread, so the cancel test is faithful.

## Live Smoke (from implement)

- Practice: attempt 1 kept printing steps after "Completing activity as failed".
  Attempts 2 and 3 overlapped it, so the 10 s job ran three times beside itself.
  The rollup, healthy geo, and receipts all completed.
- Solution: completed in one attempt.
- A scratch-only forced timeout (`STEP_SECONDS` 6.0) showed `CancelledError` raised from `_blocking_work`, with each attempt stopping at step 2.
- py-spy was not installed, so Step 10 must capture py-spy via `uvx`.

## Findings for Step 10 and Step 11

- With no heartbeat in practice, a non-local activity never learns of the server's timeout, so the Worker may never cancel the `get_location` coroutine.
  The practice marker's "cancelling the awaiting coroutine" wording may describe a cancel that never arrives, and the overlapping attempts may hold both slots.
- Step 10 must capture whether the coroutine is cancelled and whether bystanders still look fine.
  The marker wording, and the spec and plan prose saying "the coroutine is cancelled", should follow the capture.
  The duplicate-work lesson holds either way.
- Step 10 must capture py-spy via `uvx`.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Mode: implement, Step 8 | Created both exercise copies, live smoke | Tests green, duplicate work observed |
| Mode: fix, iteration 1 | Applied validator findings | Validated clean at iteration 2 |
| Mode: finalize, Step 8 | Ran both gates, wrote this summary, committed and pushed | See commit |

## Observations

- `git status --porcelain --untracked-files=all exercises/` lists only source and test files, no caches.
- No lesson added; the open question is recorded as a finding, not a settled lesson.
