# Session Summary: Correct The Frozen-Loop Diagnostic Signature

**Date**: 2026-10-04
**Duration**: One investigation-and-correction detour inside the catalog goal loop
**Conversation Turns**: Step 9 implement surfaced a spec contradiction; this is the investigation plus the spec/plan fix
**Estimated Cost**: Moderate; a live reproduction (server + worker + freeze) plus docs-MCP queries and spec/plan edits
**Model**: Fable 5 orchestrating; Sonnet 5 step-executor for the Step 9 capture (the agent definition default; the profile's model was never passed on dispatch)

## Goal Context

- **Condition**: Every item in todo.md checked; pytest -q exits 0; git status clean; all commits pushed to origin/scaffold; lessons.md has any new lessons
- **Mode**: full
- **Outcome**: in progress (paused at Step 9 for this correction)
- **Steps completed**: 8 of 10 committed; Step 9 (README) in progress

## Key Actions

- Step 9's executor captured real live output and reported that reality contradicts spec.md's headline diagnostic claim. Rather than let it ship or fabricate, the loop paused and the user chose "investigate first."
- Reproduced a live block freeze (temporalio 1.33.0, Python 3.14.3, ptrace_scope 0, real worker PID) and confirmed, with concrete evidence:
  - `py-spy dump` shows the exact blocking line: `_apply_mode (activities.py:118)` under `get_ip`, down through the event loop to `worker.py`.
  - `asyncio ps` / `pstree` truncate the wedged activity task at the SDK frame `_ActivityWorker._handle_start_activity_task` with no await beneath it, while every other task (including the rollup bystander) shows its full chain ending at a real `await` (`sleep`/`wait`/`Queue.get`).
  - The truncation is fundamental: asyncio introspection walks a task's await chain, and a task stuck in synchronous `time.sleep` is not suspended at an await, so its frames live on the OS thread stack (which py-spy reads).
  - CPU `Sl`/~0% for block (GIL released); metrics endpoint reachable during the freeze; ActivityWorker slots_available 0.
  - `temporal task-queue describe` shows the worker's poller `LastAccessTime` going stale (~38s) during a freeze rather than vanishing instantly.
- The docs MCP confirmed async activities run via a direct `await` on the shared event loop (no executor), which is why the user coroutine is reachable by py-spy but not by asyncio ps when wedged in sync code.
- User chose the two-tool story. Corrected spec.md (Starting context diagnostic signature, the block/cpu/slow and diagnostic-families entries in Behavior requirements, the Documentation requirements, and the Non-goal that said "native tooling only") and plan.md (Step 9 and Step 10) to: asyncio ps / pstree for the frozen-loop shape, py-spy dump for the exact line, CPU to separate block from cpu, task-queue backlog age and stale poller for saturation.

## Deviations from Plan

- Plan said: Step 9 captures asyncio ps showing the blocking line in user code.
- Deviated: live behavior shows asyncio ps truncates the wedged task at the SDK handler; py-spy is the tool that names the line. spec.md and plan.md were corrected to a two-tool story before the README is written.
- Impact: the demo gains py-spy as a documented read-only diagnostic (run via uvx, no project dependency); the zero-instrumentation headline now covers detection and localization-to-a-task via asyncio ps, with py-spy for the exact line.

## Process Improvements

- When a live-capture step reports the spec is wrong, pause and reproduce it directly before rewriting the design authority; the executor's finding was correct and the direct reproduction made the fix precise.

## Observations

- This is the third time live behavior corrected a written claim in this repo (after the metrics-endpoint reachability and the heartbeat-timing corrections). Capturing real output before writing prose keeps paying off.

## Suggested Skills for Next Session

- `content-design:tutorial-writing`, `content-design:review-content`: the README (Step 9) rewrite against the corrected two-tool story.
- `temporal:temporal-developer`: confirm metric names and poller semantics in the prose.
