# Session Summary: Goal Step 8, Capture Exercise 03 And The Root Reference Readings

**Date**: 2026-11-11
**Duration**: one goal step (implement, finalize); active time not tracked
**Conversation Turns**: one implement dispatch before this finalize dispatch
**Estimated Cost**: not tracked
**Model**: claude-sonnet-5-5 (the implement and finalize dispatches both ran on Sonnet, under a claude-fable-5-2 orchestrator)

## Goal Context

- **Condition**: not visible to the finalize dispatch
- **Mode**: step (Step 8 of the fleet-localization plan, a task step with `**Tools:** none`)
- **Outcome**: converged for this step (no validator pass, so no findings)
- **Subagent dispatches**: implement, finalize
- **Steps completed**: Step 8 checked off in `todo.md`

## Key Actions

Each figure below is one run, not a general result.
The raw captures, logs, and per-run readings stay in the scratchpad, outside the repository.

- Exercise 03, solution copy, one Worker, `--bad 2`: both runs took about 84.4 s (84.47 and 84.43 s), both completed on attempt 1.
  `get_location` placed 2 on the one identity.
  `top` read 81.8, 63.6, and 41.7 percent CPU at 10, 18, and 28 s.
- Exercise 03, solution copy, two Workers, `--bad 4`: four run times of 84.41, 84.43, 86.97, and 86.38 s.
  Placement was 2 and 2 for `get_location` (and for `get_ip`).
  `top` read 80.0 to 100.0 percent on both Workers.
- Retook two `py-spy dump` captures, one on the practice copy (the bug) and one on the solution copy standing in for the fixed practice copy.
  Only the last frame differs from the README: `worker.py:166` and `worker.py:168` against 115 and 117.
- Root `just healthy` only: 0 "Task not found when completing" lines in the Worker log.
- Root `just block`: 3 such lines.
  The rollup failed `ScheduleToClose`, its Activity timing out 20.0 s after it was scheduled.
  Receipt WT1 read 29,002 ms and 29,001 ms.
  `top` read 0.0 percent in state `S`.
- Workflow Task Execution Latency panel for the root `just block` run: the peak (5141.3 ms) is on the SalesRollupWorkflow line.
  The receipt line has no finite value in the window.
- `sysctl kernel.yama.ptrace_scope` reads 0.
- Exercise 02 solution fleet: retook and replaced all four `docs/images/02-solution-live-*.png` with a window that starts at the fleet start.
  Receipts read WT1 20 ms and 17 ms, and `validate_order` waits of 3227 ms and 3196 ms.
- Checked off the Step 8 boxes in `todo.md`.
- This finalize dispatch re-ran `just check` (exit 0) and `uv run pytest -q` at the root (119 passed, exit 0).

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Executor (Sonnet), `Mode: implement` | Ran the exercise 03 readings, two py-spy retakes, the root readings, and the exercise 02 fleet; replaced four images | Tree dirty with `todo.md` and four PNG files |
| Executor (Sonnet), `Mode: finalize` | Gates, session summary, three lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: start the dev server with `just server`.
- Deviated: started `temporal server start-dev --metrics-port 9465` directly in the background so the recorded PID is the server's own (the same command the recipe runs).
- Impact: none on the captures.

- Plan said: the plan lists the exercise 03 one-Worker and two-Worker readings and the root and exercise 02 readings only.
- Deviated: added by the orchestrator, two `py-spy dump` retakes (practice copy with the bug, and the solution copy standing in for the fixed practice copy) to check the `worker.py` frame lines the exercise 03 README prints.
  Only the last frame differs (115 became 166, 117 became 168).
- Impact: Step 11 corrects the README from the scratchpad files.

- Plan said: run the exercise 03 one-Worker reading once.
- Deviated: the first attempt's analysis script failed after the run, so the reading was repeated on a fresh server; the first attempt's files are kept in the scratchpad under their own name.
- Impact: none on the figures quoted.

- Plan said: retake the four 02-solution-live images and replace them, with a window that starts at the fleet start.
- Deviated: replaced all four.
  The failures image now reads "No data", and the latency image now reads 4 to 18 ms with no points near 7.8 seconds, so the alt text and the sentence beside it in the exercise 02 README (and the part 3 draft) no longer match.
- Impact: Step 11 or 13 must rewrite that caption; recorded in the scratchpad findings.

## Efficiency Insights

**What went well:**
- The py-spy retake caught a stale frame line in the README that no earlier step had checked.
- Keeping the aborted analysis run's files under their own name left no ambiguity about which run the figures come from.

**What could improve:**
- The machine had a load average of 1.9 to 4.2 and an unrelated dev server running during every run, which may explain part of the slower exercise 03 run times; this was not tested.
- The image replacement landed before the prose that captions it, so the repository holds false captions until Steps 11 and 13.

**Course corrections:**
- The orchestrator added the two py-spy retakes mid-step; the analysis script was fixed and the one-Worker reading repeated.

## Process Improvements

- When a capture step replaces an image, grep the Markdown files for its filename first and list every caption line in the commit body.
- Note the machine's load next to each timing figure, as the run times here are slower than the earlier ones.

## Observations

Every reading here is one run.
Nothing in spec.md, CLAUDE.md, any README, or any draft was changed in this step.
The writers of Steps 9, 11, 13, and 14 must write from the scratchpad captures and treat these disagreements as open.

- Exercise 03 solution, one Worker, `--bad 2`: both runs took about 84.4 s, against "about 63 seconds" at `exercises/03-cpu-bound/README.md` line 491 and 59 to 60 s at `spec.md` line 324.
  `top` read 81.8, 63.6, and 41.7 percent, against 93.0 percent at README lines 470 and 489 and 60 to 100 percent at `spec.md` line 324 (41.7 is below that range).
  `get_location` placement count was 2 on the one identity.
- Exercise 03 solution, two Workers, `--bad 4`: four run times of about 84.4 to 87.0 s, against 65 to 67 s at `spec.md` line 325.
  Placement was 2 and 2.
  The README still describes `--bad 3` at lines 496 to 538, which this run did not retake; Step 11 rewrites it.
- The py-spy retakes: the README prints `<module> (worker.py:115)` at line 197 and `<module> (worker.py:117)` at line 366; this run reads `worker.py:166` and `worker.py:168`.
  Every other frame matches.
  The fixed practice copy's `asyncio.run(main())` line depends on what the learner wrote, so Step 11 should say so or quote the solution copy's 168.
- Root `just healthy` only: 0 "Task not found when completing" lines.
  Root `just block`: 3 such lines, one for the rollup's Workflow Task at the first thaw and two for the receipts just before the final thaw (about 0.04 s before the final `get_location` completion).
  That differs from "together at the thaw" at `spec.md` lines 396 and 606.
- Root `just block`: receipt WT1 of 29,002 ms and 29,001 ms, against 28.8 s in `CLAUDE.md` and 28,816 and 28,834 ms at `README.md` line 542.
  The rollup's Activity timed out 20.0 s after it was scheduled, which matches `CLAUDE.md`.
- Workflow Task Execution Latency panel: the peak (5141.3 ms) is on the SalesRollupWorkflow line, and the receipts' 29-second stall does not appear because their first Workflow Task timed out and recorded no execution latency.
  `README.md` line 711 ("a stall of about 29 seconds reads as 5 to 6 seconds") and the matching `CLAUDE.md` dashboard fact are not supported by this run; Step 14 corrects both.
- `sysctl kernel.yama.ptrace_scope` reads 0, matching `README.md` line 723 and `spec.md` line 71.
- Exercise 02: all four `docs/images/02-solution-live-*.png` were replaced with a window that starts at the fleet start.
  The new workflow-task-latency image reads 4 to 18 ms (rollup 18, receipts about 9, geo 4), so the alt text at `exercises/02-sleep-between-heartbeats/README.md` line 683, the sentence at line 686, and the alt text at `docs/drafts/part-3-sleep-between-heartbeats.md` line 721 are now false until Steps 11 and 13 rewrite them.
  The new failures image reads "No data".
  No committed Markdown file embeds the failures, activity-latency, or slots-used image (only the workflow-task-latency image is embedded), and the old failures image showed a stale flat line left over from the practice run.
  Committing a "No data" image follows the plan's "replace the four files" instruction; whether to keep or delete that file is a build decision for Step 14.
  This run's receipts read WT1 20 ms and 17 ms and `validate_order` waits of 3227 ms and 3196 ms, against the README's printed 14 and 16 ms and 2954 and 4013 ms (lines 671 to 678).

## Suggested Skills for Next Session

- `content-design:tutorial-writing`: Step 9 is prose (README.md and the event-loop primer).
- `voice:teaching`: Mason's register on top of the tutorial canon for that prose.
- `content-design:style-linting`: the prose goes through Vale before it is committed.
