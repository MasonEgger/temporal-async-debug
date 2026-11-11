# Session Summary: Goal Step 7, Capture Exercise 06 On Two Workers

**Date**: 2026-11-11
**Duration**: one goal step (implement, finalize); active time not tracked
**Conversation Turns**: one implement dispatch before this finalize dispatch
**Estimated Cost**: not tracked
**Model**: claude-sonnet-5-5 (the implement and finalize dispatches both ran on Sonnet)

## Goal Context

- **Condition**: not visible to the finalize dispatch
- **Mode**: step (Step 7 of the fleet-localization plan, a task step with `**Tools:** none`)
- **Outcome**: converged for this step (no validator pass, so no findings)
- **Subagent dispatches**: implement, finalize
- **Steps completed**: Step 7 checked off in `todo.md` (eight boxes)

## Key Actions

- Ran three floods against a fresh dev server each, with two Workers from the named copy and Prometheus and Grafana from `just metrics`.
  Each figure below is one run, not a general result.
- Flood A (practice copy, `--bad 0`): `receipts submitted=500 failed=0`, slowest timeline bucket max 0.70 s, and both Worker logs held only the startup banner.
- Flood B (practice copy, the fourth run, the capture of record): `receipts submitted=523 failed=21` and 82 Workflow Task timeouts.
  The `--by-identity --summary` view put all 82 timeouts and all 21 failed Activities on one identity.
  The slowest receipt took 38.65 s.
  The frozen Worker's log held 95 "Task not found when completing" lines and 82 `TMPRL1104` lines.
  `TMPRL1101` appeared in no log in any flood.
  Four mid-freeze passes ran at about 0, 2, 10, and 19 seconds into the freeze, all before the thaw.
- Flood C (solution copy, the rerun, the capture of record): `receipts submitted=514 failed=0`, 0 Workflow Task timeouts on both identities, slowest receipt 0.835 s by server timestamps, median 0.405 s.
- Copied nine Grafana panel images into `docs/images/`: five `06-practice-frozen-*` and four `06-solution-live-*`.
  The raw captures, logs, and per-pass readings stay in the scratchpad, outside the repository.
- Checked off the eight Step 7 boxes in `todo.md`.
- This finalize dispatch re-ran `just check` (exit 0) and `uv run pytest -q` at the root (119 passed, exit 0).

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Executor (Sonnet), `Mode: implement` | Ran floods A, B (four runs), and C (two runs), took the readings, copied nine images | Tree dirty with `todo.md` and nine PNG files |
| Executor (Sonnet), `Mode: finalize` | Gates, session summary, three lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: start each fresh dev server with `just server`.
- Deviated: ran its command (`temporal server start-dev --metrics-port 9465`) directly in the background, so the recorded PID is the server's rather than `just`'s.
- Impact: none; same command and port.

- Plan said: take the mid-freeze readings during flood B (one flood B).
- Deviated: the first two flood B runs triggered on an `ActivityTaskStarted` history event, which the server writes only when the Activity finishes, so their readings fell after the thaw.
  A third run took only two early passes.
  The final flood B (a fourth run, on a fresh server) took four passes at about 0, 2, 10, and 19 seconds.
  The earlier runs are kept in the scratchpad under their own names and not relabeled.
- Impact: four flood B runs exist; only the last is the capture of record, and the PNG files come from it.

- Plan said: rerun flood C once if a receipt is slower than 2 seconds.
- Deviated: run 1 had 0 failures and 0 Workflow Task timeouts, but the starter's timeline printed one receipt at 2.01 s (submitted during the lead), so flood C was rerun once.
  The rerun was clean.
- Impact: flood C images and readings are from the rerun.

- Plan said: save the same panels for flood C as `docs/images/06-solution-live-<panel>.png`.
- Deviated: the failures panel reads "No data" in a clean flood, so it was not copied into `docs/images/`.
  Nine PNG files were copied, not ten.
- Impact: the README writer has no solution failures image; the empty panel is stated in text.

- Plan said: Web UI Task Queue and Workers pages as text or a note.
- Deviated: saved the Web UI backend API JSON behind the Task Queue page and did not open the rendered pages.
- Impact: the Workers tab content is not in the captures.

## Efficiency Insights

**What went well:**
- The `--by-identity --summary` view from Step 5 attributed every timeout and failure to one identity in a single command, with no hand counting.
- The one-rerun rule for flood C settled a 2.01 s outlier without a judgment call.

**What could improve:**
- Two flood B runs were wasted on a trigger that fires only after the thaw; the pending Activity state from `describe` (the starter's own gate) was the right trigger from the start.
- The machine was busy during every run (load average 4 to 6 at the start), which may have slowed flood B; it was not tested.

**Course corrections:**
- Flood B moved from a history-event trigger to a pending-Activity trigger, and from two passes to four.

## Process Improvements

- Before a capture step that reads state mid-freeze, run the trigger once on a throwaway server and check that its first pass lands before the thaw.
- Note the machine's load before each capture run, and say so next to any timing figure.

## Observations

Flood B disagrees with what spec.md says today.
Nothing in spec.md, CLAUDE.md, or any README was changed in this step.
The Step 10, 12, and 14 prose writers must write from the captures, and these are one run each.

- Backlog: `temporal task-queue describe` read 39 workflow tasks aged 3.5 s at the last mid-freeze pass (about 19 s in).
  spec.md says each single mid-freeze read showed 0.
  The passes at about 0 and 2 s did read 0, and the pass at about 10 s read 1.
- Pollers: at the last pass the frozen identity's pollers read 6 s (workflow) and 8 s (activity) stale while the other Worker's read current.
  spec.md and CLAUDE.md say poller last-access time does not mark the frozen Worker.
  At the earlier passes both identities read current or 1 to 2 s old.
- Slowest receipt: 38.65 s, against 20.7 to 21.5 s in spec.md.
  Every timeline bucket from +20 s to +40 s still read 49 or 50 of 50 slow, so the fleet did not look recovered before the thaw.
  Earlier flood B runs read a slowest bucket max of 34.05 s, 21.1 s, and 23.64 s.
- `receipt-gaps` took 49.9 to 63.6 s for 523 receipts, against 37.7 s for 518 in the spec.
- Metrics response times at the last pass: 35.1 ms on the frozen Worker and 2.8 ms on the other; 6.0 ms on the other Worker at the third pass.
  spec.md says about a millisecond.
  Both still answered in milliseconds.
- Gap: the rendered Web UI Task Queue and Workers pages were not opened.
  The Task Queue page's backend API JSON was saved instead, so there is no Workers tab reading from this step.
- Gap: the solution failures panel reads "No data" in a clean flood, so there are nine images, not ten.
  The prose states the empty panel.

## Suggested Skills for Next Session

- `content-design:tutorial-writing`: Step 8 is the exercise 03 recapture, and the steps after it write exercise READMEs and draft parts from these captures.
- `temporal:temporal-developer`: Step 8 is another live capture step on the Temporal CLI dev server.
