# Session Summary: Gate Freeze-Path Bystanders on the Activity STARTED

**Date**: 2026-10-07
**Duration**: One correction pass outside the plan (implement, three validator iterations, two fix rounds, finalize)
**Conversation Turns**: Orchestrated; one implement dispatch, two fix dispatches, three validator dispatches, one finalize dispatch
**Estimated Cost**: Moderate; a focused starter change plus new starter tests and three validator passes
**Model**: Implementer Opus 5.5; validator Fable 5.1 (three iterations, clean at iteration 3); finalize Opus 5.5

## Key Actions

- A live re-run after dd1b6c4 showed the freeze recipes' instant bystanders racing.
  Receipts submitted right after the bad geo run failed ScheduleToStart in 5 of 6 runs and stalled in 1 of 6.
  They failed when their first workflow task slipped in before time.sleep locked the loop, then their activity was scheduled while both slots were held.
- Design decision: the in-flight rollup is the run's one deterministic cross-type failure, and the instant bystanders must deterministically stall and complete late.
- starter.py: new `wait_for_activity_started(handle)` polls `handle.describe()` every 0.25s, up to 80 attempts, for a pending activity in `PendingActivityState.STARTED`.
  describe() is a client-to-server call, so the frozen worker cannot block it.
- `_submit_freeze_scenario` gates receipts and quotes behind that STARTED signal plus a 1.0s guard (`FREEZE_LOCK_GUARD_SECONDS`), so their first workflow task cannot run until the thaw.
- Fallbacks: when describe() raises `RPCError`, the gate waits on the slot gauge with target `max(0, baseline_free - (1 if has_early_bystanders else 0) - 1)`.
  When metrics are also unreachable, it pauses 3.0s blind (`FREEZE_FALLBACK_DELAY_SECONDS`).
  Every ungated or unconfirmed path prints a warning ending in "the loop may not be locked, so the receipts and quotes may complete on time instead of stalling".
- receipt.py: module docstring now says the receipt times out behind saturated slots or stalls behind a frozen loop and completes late.
- Tests: starter tests cover the STARTED gate, the describe-fails gauge fallback and its target, the blind pause with metrics down, the warning text, and the instant-only fleet.
  117 tests became 122; `just check` is green.

## Deviations from Plan

- Plan said: in the freeze path, submit receipts and quotes right after the bad geo run, so they stall behind the frozen loop.
- Deviated: a live re-run against dd1b6c4 showed they raced: 5 of 6 failed ScheduleToStart (activity scheduled while both slots were held, before time.sleep locked the loop) and 1 of 6 stalled.
  The first fix gated the instant bystanders on the ActivityWorker gauge reading 0 free (`wait_for_free_activity_slots(0)`) plus a 1.0s guard, with a 3.0s blind pause when metrics were unreachable.
  The gate runs only when the fleet has receipts or quotes.
  Docstrings updated in starter.py (module, FREEZE_MODES, freeze function) and receipt.py (module).
- Impact: instant bystanders stall and complete late on every freeze run; the in-flight rollup stays the one cross-type failure (ScheduleToClose caused by StartToClose).
  The freeze path adds about 1s.
  Tests patch asyncio.sleep, so none of them actually sleep.
- Plan said (validator iteration 1, block on the gauge target and warn on gauge semantics): replace the gauge-based lock gate with a server-side STARTED signal.
- Deviated: added `wait_for_activity_started(handle)`, comparing `int(pending.state)` to `PendingActivityState.STARTED` because the proto enum type does not overlap the SDK IntEnum for mypy.
  The poll is bounded by an attempt count (`round(LOCK_POLL_TIMEOUT_SECONDS / LOCK_POLL_INTERVAL_SECONDS)` = 80), not a wall-clock deadline, so tests that patch asyncio.sleep terminate; slow describe() round trips stretch it slightly past 20s.
- Deviated: the gate now uses STARTED even when metrics are unreachable (describe() needs only the server).
  The gauge fallback runs only when describe() raises `RPCError`, with a target that accounts for an early bystander holding a slot; the 3.0s blind pause runs only when describe() raises and metrics are down.
- Deviated: dropped `test_freeze_lock_delays_leave_time_for_the_lock`; the fallback-versus-guard ordering assertion now lives in the describe-raises-and-metrics-down test.
- Impact: an instant-only freeze fleet no longer burns the 20s poll.
  The live freeze run was not re-run; the STARTED-to-lock latency is inferred from the activity body, not captured.
- Plan said (validator iteration 2, warn on fallback warning text; iteration 3 came back clean): the describe()-fails-and-metrics-down branch printed "falling back to the activity slot gauge" and then took the blind pause with no gauge read and no consequence text.
- Deviated: the describe() warning moved inside the branches.
  With no metrics baseline it prints "describe() failed (...) and the metrics endpoint is unreachable; pausing 3.0s blind; the loop may not be locked, ..."; the gauge branch keeps "falling back to the activity slot gauge".
  The matching test takes capsys and asserts the new text, the consequence, and the absence of the gauge wording.
- Impact: message-only change; event order and timing unchanged; 122 passed.

## Efficiency Insights

**What went well:**
- A live re-run caught a race that the unit tests could not, and its 5-of-6 count made the design decision easy to state.
- Patching asyncio.sleep and bounding the poll by attempts kept the new gate fully testable without real waits.

**What could improve:**
- The first fix reached for the slot gauge, which cannot say which activity holds a permit; checking what the gauge measures before using it as a lock signal would have saved a validator round.

**Course corrections:**
- Gauge as primary signal replaced by describe() STARTED after the validator's block finding; the gauge survives only as a fallback.

## Process Improvements

- Before using a metric as a gate, confirm it can distinguish the event you care about from others that move it the same way; when it cannot, look for a server-side state instead.

## Observations

- spec.md, CLAUDE.md, plan.md, and todo.md carry a separate docs stream's uncommitted edits and were left out of this commit on purpose.
- The STARTED-to-lock latency and the end-to-end "instant bystanders always stall" behavior still need a live capture to confirm.

## Suggested Skills for Next Session

- `temporal:temporal-developer`: a live re-run of the block and cpu recipes to confirm the instant bystanders stall on every run.
- `content-design:tutorial-writing`: the docs stream's README and spec text should describe the STARTED gate and the warning paths.
- `python:python`: any follow-up starter change under strict mypy.
