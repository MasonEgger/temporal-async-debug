# Session Summary: Gate Freeze Bystanders on the Last Freezing Activity

**Date**: 2026-10-07
**Duration**: One correction pass outside the plan (implement, one validator iteration, finalize)
**Conversation Turns**: Orchestrated; one implement dispatch, one validator dispatch, one finalize dispatch
**Estimated Cost**: Moderate; a focused starter change, new starter tests, and one validator pass
**Model**: Implementer Opus 5.5; validator Fable 5.1 (clean at iteration 1); finalize Opus 5.5

## Key Actions

- A 7-run live measurement of the 6e4e433 gate showed it was exact for the first freeze: 16 of 16 bystanders' first workflow task landed about 1.25s after the lock.
- The same runs exposed a second race.
  The bad geo workflow freezes twice (get_ip, then get_location) with only about 140ms of live loop between the freezes.
  A bystander released at the first thaw could be dispatched just as the loop re-froze; 1 of 16 failed ScheduleToClose caused by StartToClose.
  The healthy geo could also lose the race to the first lock when its HTTP call was slow.
- starter.py: `wait_for_activity_started(handle, activity_type, timeout_seconds)` now matches a pending activity by name and state.
  The freeze path passes `FREEZE_GATE_ACTIVITY`, pinned to `get_location.__name__`, so receipts and quotes stall through the final freeze and complete at the thaw with no re-freeze left to race.
- New pure function `lock_poll_timeout_seconds(block_seconds)` returns `max(20s, block_seconds + 10s)`, since get_location cannot start until get_ip's freeze ends.
- `_submit_freeze_scenario` awaits the healthy geo runs (new `_await_completion` helper) before submitting the bad run, so only the rollup holds a slot when the first freeze lands.
- The describe()-fails gauge fallback and the blind-pause fallback stay, and every warning still names its consequence; the gauge warning now says the gate is approximate because the gauge cannot tell get_location from get_ip.
- Tests: 122 became 128; `just check` is green.

## Deviations from Plan

- Plan said: gate the freeze path's instant bystanders on get_location (the bad run's second activity) reporting STARTED, with a block_seconds-scaled poll budget, and await the healthy geo before submitting the bad run.
- Deviated: wait_for_activity_started takes a third argument, timeout_seconds, fed by a new pure function lock_poll_timeout_seconds(block_seconds) = max(20s floor, block_seconds + 10s); the block_seconds comes from fleet.bad_geo[0], since _submit_freeze_scenario receives the fleet, not args.
  LOCK_POLL_TIMEOUT_SECONDS became LOCK_POLL_MIN_TIMEOUT_SECONDS plus LOCK_POLL_DISPATCH_MARGIN_SECONDS.
- Deviated: the healthy geo await is a small helper, _await_completion, that suppresses WorkflowFailureError, because _report_results awaits the same handles later and prints any failure in the unchanged report order.
- Deviated: the gauge fallback's lock target now subtracts the extra slot only when rollups exist (the healthy geo has finished by then), so a healthy-geo-only fleet targets baseline - 1.
- Deviated: the registered-name test reads activity._Definition.must_from_callable(get_location).name, a private SDK helper (noqa SLF001), because the SDK exposes no public accessor for a definition's registered name.
- Impact: the never-STARTED warning now names get_location and the computed timeout; just check green (128 passed).
  Not live-verified against a server in this dispatch.

## Efficiency Insights

**What went well:**
- The 7-run live measurement split one symptom into two causes (re-freeze race, healthy geo losing the lock race), and each got its own targeted fix.
- The validator came back clean on the first iteration.

**What could improve:**
- The earlier gate assumed one freeze per bad run; reading the workflow's activity sequence before choosing the gate activity would have caught the double freeze one round sooner.

**Course corrections:**
- None inside this pass.

## Process Improvements

- When gating on a freeze, list every freezing activity in the workflow and gate on the last one, not the first.

## Observations

- spec.md, CLAUDE.md, plan.md, and todo.md carry the docs stream's uncommitted edits and were left out of this commit on purpose; implementation-notes.md keeps its "## Fix B" section for that stream.
- The new gate still needs a live capture to confirm every instant bystander stalls through the final freeze and completes.

## Suggested Skills for Next Session

- `temporal:temporal-developer`: a live re-run of the block and cpu recipes to confirm the get_location gate across several runs.
- `content-design:tutorial-writing`: the docs stream should describe the double freeze and the last-activity gate.
- `python:python`: any follow-up starter change under strict mypy.
