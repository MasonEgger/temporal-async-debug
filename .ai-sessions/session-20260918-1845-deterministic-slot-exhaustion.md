# Session Summary: Make the Slot-Exhaustion Lesson Fail Deterministically

**Date**: 2026-09-18
**Duration**: Follow-up session, roughly 45 minutes
**Conversation Turns**: 1 user turn
**Estimated Cost**: Moderate; Temporal docs MCP queries plus one live-verification subagent (two full slow runs)
**Model**: Fable 5 orchestrating; Sonnet subagent for the live verification

## Key Actions

- Consulted the Temporal docs MCP on heartbeating long-running activities, schedule-to-start semantics, and max_concurrent_activities. Confirmed: long-running activities must heartbeat at an interval a few times shorter than heartbeat_timeout to keep their slot; schedule_to_start_timeout is officially "usually should not be set" and is non-retryable, which is exactly why it fits the deliberate antipattern; a worker with full slots stops polling and drops off the UI poller list.
- Fixed the race in the slot-exhaustion lesson two ways: slow-mode activities now heartbeat every 3 seconds during their sleep (SLOW_HEARTBEAT_INTERVAL_SECONDS) so they hold their slot for the full duration instead of being cancelled at the 10 second heartbeat_timeout; and the starter now sequences the slow scenario, starting the greetings first, polling the metrics endpoint until ActivityWorker free slots reach 0, then submitting the victims so they cannot get a slot.
- Guarded the new heartbeat with activity.in_activity() so the Temporal-free starvation-probe test still calls _apply_mode bare without crashing.
- Updated tests: slow-mode activity tests now assert the total cooperative sleep and the repeated slot-holding heartbeats; added a metrics-parser unit test (including that it reads ActivityWorker and not LocalActivityWorker) to test_starter.py. Full gate green: 39 tests, ruff, ruff format, mypy strict.
- Verified live (subagent, two runs): 3 of 3 victims failed on schedule-to-start every run, 0 successes; ActivityWorker slots hit 0 within ~2 seconds and stayed 0 for 36 seconds (well past the old 10 second pop-back); no heartbeat-timeout cancellations of the slow greetings.
- Updated README Step 3 and spec.md to describe the deterministic behavior and removed the now-false "10 to 14 second window" caveat.

## Deviations from Plan

- The live greetings failed at get_location with HTTP 429 from ipapi.co (rate-limited from repeated dev-loop testing), after holding their slots for the full sleep. This is a network artifact, not a logic issue, and does not affect the victim or slot verification.

## Findings To Act On

- OPEN (new, separate from this fix): on one of the two live runs, the starter printed all its results and then hung on exit instead of returning (0% CPU, futex_wait, teardown-time), and had to be killed. It looks like a client or Core runtime teardown issue on process exit, possibly involving the added httpx metrics client or the Temporal client, and it is intermittent. A hanging `just slow` is bad for the tutorial and should be diagnosed (bisect: does the old execute_workflow path hang too, does removing the httpx metrics poll change it, does an explicit client shutdown fix it) before publishing.
- STILL OPEN (from prior sessions): the asyncio ps capture placeholder in the README needs a real capture from a ptrace_scope=0 machine.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| "double check with the temporal MCP, don't have anything race, obvious failure, bump timing if needed" | Queried Temporal docs, added slow-mode heartbeating and starter slot-poll sequencing, verified live | Slot-exhaustion failure is now deterministic; 3/3 victims fail every run |

## Observations

- The elegant part of the fix: GreetingWorkflow keeps one set of timeouts (heartbeat_timeout=10s, maximum_attempts=1). The only difference between the two lessons is time.sleep versus asyncio.sleep-plus-heartbeat. Block mode cannot heartbeat because the loop is frozen, so it dies at the heartbeat timeout; slow mode heartbeats and holds its slot. Same config, opposite outcome.

## Suggested Skills for Next Session

- `temporal:temporal-developer`: to diagnose the starter exit hang (client/runtime teardown).
- `python:python`: for any starter or activity code changes.
