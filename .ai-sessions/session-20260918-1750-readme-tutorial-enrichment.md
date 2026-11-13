# Session Summary: Turn the README Into the Tutorial Home

**Date**: 2026-09-18
**Duration**: Follow-up session after the build loop, roughly 30 minutes
**Conversation Turns**: 2 user turns
**Estimated Cost**: Moderate; two live-capture subagents and one copy-editor agent
**Model**: Fable 5 orchestrating; Sonnet subagents for the live captures; the content-design copy-editor for the style pass

## Key Actions

- Read the shipped README and judged it honestly: already tutorial-shaped and hard-rule compliant, but it described diagnostic output instead of showing it, and its Lesson 2 timing was wrong.
- Confirmed with the user that the README should become the tutorial home and that the copy-editor should review and apply.
- Captured real metrics output live (subagent): healthy `ActivityWorker` slots = 2, exhausted = 0, verbatim; endpoint reachable on 14 of 14 scrapes during exhaustion; real schedule-to-start metric name `temporal_activity_schedule_to_start_latency`.
- Enriched README.md into a tutorial: outcome-focused introduction, Prerequisites, three Steps (start server and Worker, reproduce the frozen loop, reproduce the exhausted slots), a distinguishing summary, and a recap. Embedded the real metrics blocks with code-sandwich explanation.
- Ran the content-design copy-editor with apply: 0 Vale errors afterward, protected blocks left verbatim, Mason's author-voice touches added (contractions, forward-motion transitions).

## Deviations from Plan

- `python -m asyncio ps` output could not be captured on the build machine: Linux `ptrace_scope=1` and no passwordless sudo, so the inspector fails with "Failed to find the PyRuntime section" even on a child process. The README carries a clearly-labeled `<!-- CAPTURE NEEDED -->` placeholder for a real capture from a `ptrace_scope=0` machine rather than invented output.

## Findings To Act On Before Publishing

- OPEN (demo tuning): with `--block-seconds 30` but `GreetingWorkflow`'s `heartbeat_timeout=10s` and `maximum_attempts=1`, the slow-mode Activities are cancelled on heartbeat timeout at about 10 seconds, so both slots free up around 10 to 14 seconds, not the full 30. The README now states this accurately. It also means the slot-exhaustion window races the victim's 10 second `schedule_to_start_timeout`, so the victim-timeout demonstration is tight. Consider a demo change before the tutorial publishes: have slow mode heartbeat periodically during the sleep so the slot is held for the full duration, or lengthen the heartbeat timeout, or shorten the victim's schedule-to-start. Not changed here; it is a design decision.
- OPEN (from the prior session): the `asyncio ps` capture placeholder needs filling from a ptrace-enabled machine.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| "Do you have the README in my style? part of the tutorial will live in the readme" | Read and assessed the README, asked direction | User chose: make README the tutorial home, copy-editor review and apply |
| (direction given) | Captured real metrics, enriched README, ran copy-editor with apply | Tutorial-shaped README, 0 Vale errors, real output blocks, timing corrected |

## Observations

- The live capture paid off twice: it produced the genuine slots=0 line for the tutorial and it exposed the heartbeat-timeout-shortens-exhaustion timing that the written spec and the first README draft both missed.

## Suggested Skills for Next Session

- `content-design:tutorial-writing` and `content-design:copy-editor`: any further tutorial prose work.
- `temporal:temporal-developer`: if the demo timing gets tuned (heartbeats in slow mode, timeout changes).
