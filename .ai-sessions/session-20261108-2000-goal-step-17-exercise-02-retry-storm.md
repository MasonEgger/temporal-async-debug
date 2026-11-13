# Session Summary: Step 17 Exercise 02 Visible Retry Storm

**Date**: 2026-11-08
**Duration**: about 60 minutes
**Conversation Turns**: autonomous /bpe:goal step (implement, validate, fix, finalize)
**Estimated Cost**: not tracked
**Model**: claude-sonnet-5-5

## Goal Context

Driven by `/bpe:goal` over plan.md Section 9 (Post-Review Rework). This session covers Step 17 only.

## Key Actions

- Rebuilt exercise 02 (`exercises/02-sleep-between-heartbeats`) so the Heartbeat timeout produces a visible retry storm.
- Added an awaited async status check, `_job_is_done` (with `await asyncio.sleep(0)`), that runs before each heartbeat and blocking poll.
- `JOB_SECONDS` is now 60.0, keyed on the run id so every attempt works on the same job.
- Rewrote the ANTIPATTERN marker in the practice copy; the solution keeps the 1 s awaited tick loop and carries no marker.
- New solution tests: the same job across attempts, and the status check yielding to the loop.
- Validator passed clean at iteration 2, after one fix pass that gave the yield test teeth.
- Live smoke run: Attempt reached 4 on Heartbeat timeout (captures in the scratchpad `captures/s17/`).
- `just check` and `just check-practice` both exit 0.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| mode=implement, Step 17 | Status check, 60 s job, marker, tests | Tests green |
| mode=fix, iter 1 | Gave the yield test teeth | Re-validated clean |
| mode=finalize | Gates, summary, lesson, commit, push | One signed commit |

## Efficiency Insights

- The smoke run is the only proof the retry storm is visible; unit tests shrink the 60 s job.

## Process Improvements

- The new tests call the private `_job_is_done` directly. Nothing checks that `get_location` builds the key from the run id rather than the attempt. An `ActivityEnvironment` test driving `get_location` twice with the same run id would cover it (info finding).

## Observations

- TMPRL1101 "Potential deadlock detected" is timing-dependent. The earlier spike logged it twice; the Step 17 smoke run logged 0 of it and 4 TMPRL1104 lines (workflow task duration exceeded). spec.md says the exercise 02 Worker log shows TMPRL1101 (lines 252 and 345; plan.md 751, 783, 923, 957); that should become "can show". Step 19 should count appearances across more than one run, then Step 20 edits the wording.

## Suggested Skills For Next Session

- python:python
