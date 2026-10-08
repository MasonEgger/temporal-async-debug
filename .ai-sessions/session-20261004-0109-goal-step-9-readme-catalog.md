# Session Summary: Step 9, Comprehensive README Catalog

**Date**: 2026-10-04
**Duration**: One implement, validate, copy-edit, finalize pass inside the catalog goal loop
**Conversation Turns**: Step 9 implement (live captures plus README rewrite), validator pass (clean at iteration 1), finalize
**Estimated Cost**: Moderate; live server and worker runs for captures, one py-spy capture, Vale pass
**Model**: Fable 5 orchestrating; Sonnet 5 step-executor (agent default) for implement and finalize

## Goal Context

- **Condition**: Every item in todo.md checked; pytest -q exits 0; git status clean; all commits pushed to origin/scaffold; lessons.md has any new lessons
- **Mode**: full
- **Outcome**: in progress
- **Steps completed**: 9 of 10 (this commit finishes Step 9)

## Key Actions

- Rewrote README.md as the in-repo tutorial home for the catalog: one lesson per scenario, each built from real captured output (`asyncio ps`, `pstree`, `py-spy dump`, CPU state, Prometheus metrics, `temporal task-queue describe`).
- Taught the corrected two-tool diagnosis: `asyncio ps` / `pstree` show the frozen-loop shape (the wedged task dead-ends at the SDK handler while every other task sits at a real await), and `py-spy dump` names the exact blocking line. CPU separates `block` (low, GIL released) from `cpu` (busy).
- Took one new live py-spy capture for the `cpu` mode (activities.py:124, thread active and holding the GIL), since none existed.
- Resolved and removed the three CLAUDE_HELP flags from the first pass before commit: the user-frame question was answered by the two-tool story, the poller claim was rewritten, and the Yama/macOS text was stated as documented behavior.
- Checked off the Step 9 items in todo.md.
- Full gate (`just check`) green: 74 passed.

## Prompt Inventory

| Prompt | Action | Outcome |
|---|---|---|
| Step 9 implement | Captured live output, rewrote README | README matches observed behavior |
| Validator pass | Independent check against spec fences | Clean at iteration 1, no info findings |
| Finalize | Gate, summary, commit, push | One signed commit |

## Deviations from Plan

- Plan said: capture real `asyncio ps`/`pstree` output; spec says the blocking task's stack ends in user code at the `time.sleep` / cpu loop call site.
- Deviated: on Python 3.14.3 the running (frozen) task showed only `_ActivityWorker._handle_start_activity_task` (_activity.py:351); no user frame. The README documents the observed shape (stale parked `roll_up_sales` sleep plus a truncated running task) and flags it with CLAUDE_HELP. spec.md and CLAUDE.md still claimed a user-code frame at that point; spec.md and plan.md were then corrected in 12b613f.
- Impact: README says to use a sampling profiler (py-spy) to find the blocking line. CLAUDE.md's architecture prose still carries the older claim; Step 10 or a follow-up should align it.
- Plan said: starved bystanders trip schedule_to_close; schedule_to_start latency climbs during saturation.
- Deviated: observed failure label for receipts, rollups, quotes under saturation is `ScheduleToStart` (server label for never-started Activities); the SDK latency histogram only records when a queued task finally starts, so it did not climb in a 30s `slow` run (sum 1569 to 1574 ms) but did in `just slow 12` (1620 to 15779 ms). `temporal task-queue describe` backlog age (7.3s, 13.4s) is the live signal and is quoted instead.
- Impact: freeze scenarios: only the rollup (in-flight) fails (ScheduleToClose caused by StartToClose); geo bystanders complete because geo start_to_close is 120s. The starter's freeze scenario does not report receipts.
- Plan said: verify metric names and poller-vanishing via the temporal-docs MCP.
- Deviated: the MCP tool was not callable from the subagent; metric names verified against live /metrics output and the temporal skill's go observability reference. Poller-vanishing in the Web UI not verified (CLI capture inconclusive); README does not claim it as fact. Yama/macOS error text not reproduced (ptrace_scope is 0 here).
- Plan said: review-content runs Vale plus copy-editor agent.
- Deviated: no Agent tool in that context, so Vale and the keyboard-characters check ran, and the copy-editor pass was done by hand; a full content-design:copy-editor agent pass then ran from the parent session (one numeral change; Vale warnings triaged). Remaining Vale warnings: CodeLineLength on verbatim captured output, heading capitalization (sentence case is required for this doc), 'deliberately' weasel word (spec phrase), Flesch score.
- Impact: known, accepted Vale warnings on the README.
- Plan said: reuse scratchpad captures; recapture only if missing.
- Deviated: no py-spy capture existed for cpu mode (earlier py-spy attempts were permission denied), so one was taken live (server + worker, then torn down, ports freed): `pyspy-cpu.txt` in the scratchpad showing activities.py:124, thread active+gil.
- Impact: Lesson 3 quotes a real cpu dump. Lesson 2 now pairs the asyncio-ps-block/pyspy-block captures (PID 3125455).
- Plan said: stale poller LastAccessTime is the saturation tell.
- Deviated: the freeze capture (38s) equals the idle capture (38s), so README states a single reading is ambiguous and the signal is growth across readings. The "eventually drops off" moment was not captured and is stated as such.
- Impact: backlog age and slots gauge are the primary tells in the README.

## Process Improvements

- A tutorial's live-output claims must be captured and re-verified whenever the SDK or runtime version changes. The diagnostic signature shifted (`asyncio ps` truncation of a wedged task) between the original research and temporalio 1.33.0 / Python 3.14.3, and only a live capture exposed it. Candidate lesson for lessons.md (not appended in this commit; the finalize dispatch staged only README.md, todo.md, and this summary, and the 2026-10-04 lessons already cover the truncation fact itself).

## Observations

- Single-reading metrics (poller LastAccessTime) can look identical between idle and frozen; teach the trend across readings, not the snapshot.
- Remaining Vale warnings are structural to the doc (verbatim output, required heading case), not prose defects.

## Suggested Skills for Next Session

- `content-design:review-content`: re-check README after any follow-up edits.
- `python:python`: Step 10 touches project configuration and CLAUDE.md alignment.
