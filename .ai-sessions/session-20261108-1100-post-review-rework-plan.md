# Session Summary: Post-Review Rework Plan and ptrace Capture

**Date**: 2026-11-08
**Duration**: about 3 hours across one compaction
**Conversation Turns**: about 20 user turns
**Estimated Cost**: about $25 (Opus 5.5 for most of the session, Sonnet 5.5 at the end)
**Model**: claude-opus-5-5, then claude-sonnet-5-5 for the final turns

## Key Actions

- Put every open review question to Mason through AskUserQuestion and recorded the rulings: rework exercise 02 for a visible retry storm, keep zlib in exercise 05 over realistic audit lines, commit a receipt-gap script, ship a metrics-port setting for exercise 03, keep the exercise 04 forced-timeout demo as a described extension, capture root histories, keep the 4 s heartbeat cadence cut, capture the ptrace failure, and turn off MasonBase.Headings for exercises and drafts.
- Answered Mason's question on spec drift: two items were real departures (02 was not a storm, 05 swapped JSON for zlib), and two were predictions corrected in detail.
- Ran a spike on exercise 02 that showed a visible storm inside the frozen-loop scope: an awaited status check before each blocking poll, with Attempt climbing past 2 in the Web UI and TMPRL1101 in the Worker log.
- Confirmed that exercise 05 passes only `str` and `int` across Temporal boundaries; the audit trail stays inside the Worker.
- Appended Section 9 "Post-Review Rework" (Steps 14 to 19) and Section 10 "Rework Prose" (Steps 20 to 22) to plan.md, and 60 matching checkboxes to todo.md.
- Captured the ptrace failure and recovery against an idle root Worker: under `ptrace_scope` 1, `uvx py-spy dump` printed "Permission Denied" and `python -m asyncio ps` printed "cannot be attached to due to insufficient permissions". Under 0, both attach. The files live in the scratchpad `captures/root-ptrace/` with INDEX rows.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| "What questions do you need me to rule on?" | Batched the open review questions into AskUserQuestion | Rulings on 02, 05, gap helper, 03 port, 04 demo, root capture, heartbeat cut |
| Spec drift question | Separated real departures from corrected predictions | Mason chose to spike 02 before deciding |
| "Temporal doesn't write to the history but you can see it failing in the UI" | Corrected my claim; added UI screenshots to the plan | Step 19 captures `02-practice-ui-<view>.png` |
| 05 serializability question | Checked the signature and payload path | Nothing binary crosses a boundary; realistic lines plus a note |
| "Ask me all questiosn using AskUserQuestionTool" | Second question batch | Rebuild 02 on the spike, call out TMPRL1101, append steps and run /bpe:goal |
| `! sudo sysctl ...` | Explained that `!` cannot prompt for a password, and the key typo | Mason ran it in his own terminal |
| "did that work ... system level flag" | Read `/proc/sys/kernel/yama/ptrace_scope` | It read 1; captured the failures |
| "done" | Captured the recovery at scope 0, stopped the server and Worker, and wrote INDEX rows | Capture complete |

## Efficiency Insights

**What went well:**
- The spike settled the exercise 02 design with evidence before plan text was written.
- Reading the sysctl from `/proc` answered "did that work" without another round trip.

**What could improve:**
- I first called `uv run py-spy`, which fails because py-spy is not a project dependency; the README already says `uvx py-spy`.
- I suggested a `!` sudo command, which cannot work because sudo has no terminal to prompt on.

**Course corrections:**
- Mason corrected my claim that a retry storm cannot be seen: the Web UI shows the failing attempts.

## Process Improvements

- For any step that needs sudo, tell the user to run it in their own terminal, then verify the effect from this session.
- Before running a tool in a capture, grep the README for its documented invocation.

## Observations

- `pkill` with a pattern that matches the calling shell exited 144 again; `pgrep ... | grep -v pgrep` was the safe check.

## Suggested Skills for Next Session

- `python:python`: Steps 15 to 18 add scripts/receipt_gaps.py, the port setting, and the 02 and 05 rewrites.
- `temporal:temporal-developer`: the 02 storm design, TMPRL1101, and the describe and UI readings.
- `content-design:tutorial-writing` and `voice:teaching`: Steps 20 to 22 rewrite READMEs and drafts.
- `content-design:review-content`: the prose validator pass for Section 10.
