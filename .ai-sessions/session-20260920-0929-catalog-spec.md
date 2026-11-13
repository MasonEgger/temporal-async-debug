# Session Summary: Expand the Spec to the Full Failure-Mode Catalog

**Date**: 2026-09-20
**Duration**: Short, part of the larger design-and-build session
**Conversation Turns**: continuation of the catalog design discussion
**Estimated Cost**: Low; a spec rewrite plus Temporal docs verification earlier in the arc
**Model**: Fable 5

## Key Actions

- Rewrote spec.md from the two-lesson design into a comprehensive catalog of the ways a shared asyncio event loop in a Temporal Python worker gets wedged, per the user's request for an exhaustive demo.
- Recorded the live-verified timeout mechanics in Starting context so the build respects them: uncancellable blocks hold their slot for the full duration (time.sleep releases the GIL, a CPU loop pins it); async awaits are cancelled at start_to_close; a frozen loop freezes workflow-task scheduling too, so only already-scheduled or in-flight work trips activity timeouts and instant work only stalls; the metrics endpoint stays reachable during a freeze; the starter needs os._exit to avoid the SDK teardown hang.
- Added a Design principles section (no labeled roles, mode-as-data, realistic timeouts, exhaustive-but-grounded) and a Foundation already in place section so the plan builds the delta on top of the committed two-workflow foundation.
- Defined the target architecture and a scenario catalog: misbehavior modes block, cpu, slow, slow_heartbeat, stuck_no_heartbeat; instant and short-work bystander shapes; a schedule-to-start sample; every activity timeout (start_to_close, schedule_to_close, schedule_to_start, heartbeat) shown firing; the frozen-loop vs saturated-worker diagnostic split; cross-type blast radius.
- Moved the cpu-bound and heartbeat variants out of v2 future work into this arc; kept the fleet generator, seeded culprit, and FastAPI game master as v2.
- Updated Test and Documentation requirements to match, including a per-scenario README lesson, a mode-to-timeout-to-signature table, and a CLAUDE.md architecture refresh.

## Deviations from Plan / Deferred

- README.md and CLAUDE.md remain deferred to the catalog build (they are stale relative to the committed foundation) so they are written once against the final live-verified behavior.

## Next steps

- User runs /bpe:plan to generate plan.md and todo.md from this spec. The spec's Foundation already in place section should let the plan target the catalog additions; any foundation-covered steps get marked done in todo.md before /bpe:goal.
- Then commit plan.md and todo.md, and run /bpe:goal to set up the autonomous build loop (validator + live-verify per step), which retunes timeouts against live behavior and writes the comprehensive README last.

## Suggested Skills for Next Session

- `python:python`, `temporal:temporal-developer`: the catalog build adds modes, activities, workflows, and tests.
- `content-design:tutorial-writing`, `content-design:review-content`: the comprehensive README lesson set.
