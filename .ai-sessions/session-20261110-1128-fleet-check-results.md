# Session Summary: Fleet Check Results

**Date**: 2026-11-10
**Duration**: late morning; active time not tracked
**Conversation Turns**: no new user turn; the work follows the four rulings of the same morning
**Estimated Cost**: not tracked; the session crossed two more context summaries
**Model**: claude-fable-5-2

## Key Actions

- Ran the fleet checks the spec still listed as missing, as scratch spikes against the dev server, and saved the raw output outside the repository.
- After-fix flood: a solution-shaped scratch copy ran the bad flood six times on two Workers.
  Five runs failed no receipt and timed out no Workflow Task; one run was slow with no failure, and its cause was not identified.
- Seventh freeze run on the practice-shaped copy, with Prometheus scraping both Workers.
  It fell inside the spec's ranges except in two timeline buckets.
- Ran `scripts/receipt_gaps.py` as it stands on that run's 518 receipt histories and compared each line with the saved records.
- Read all six dashboard panels and a scratch per-Worker panel from Prometheus for the freeze window, and took Web UI screenshots after the thaw.
- Reran exercise 03's solution on two Workers, twice with `--bad 2` and twice with `--bad 4`, and saved the per-identity placement this time.
- Wrote the results into spec.md in place of the "not measured" and "not saved" notes, with three new decisions marked for review.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| (no prompt; follows from the ruling "fix, measure, then plan") | Ran five scratch spikes and recomputed every figure from the saved files | Results for the after-fix flood, the helper, the dashboard, the Web UI, and exercise 03's placement |
| (no prompt; same ruling) | Edited spec.md with an exact-match script and ran the gates | Twelve edits; Vale alert count unchanged at 188; `just check` green |

## Efficiency Insights

**What went well:**
- Every spike saved its records, logs, and tool output before its processes stopped, so each spec figure could be recomputed from a file.
- Recomputing after a context summary caught two figures the summary had wrong (260 slow receipts, not 259; the fourth flood of five, not the fifth).
- The timeline buckets of the seventh freeze run were checked against the starter's own printed table before the spec sentence was kept.

**What could improve:**
- The Web UI check ran about four minutes after the thaw, so it says nothing about what the pages show during a freeze.
- The slow after-fix run was not reproduced, so its cause is open; the spec records it as one run with an unknown cause.
- Exercise 03's reruns shared the machine with other work (a load average of 6.8 on four cores), so their timings are slower than the earlier ones and the two sets cannot be pooled.

**Course corrections:**
- None from Mason in this session.
- The earlier inference that two bad runs on two Workers split one per Worker did not hold: both ran on one Worker in two of two saved invocations.
  The spec now says so, and the decision to run four stands.

## Process Improvements

- After any context summary, recompute each figure from the saved files before it goes into the spec or a report.
- Start a fresh dev server for each capture flood, and record the order of runs on a server next to their results.
- Take Web UI and dashboard captures during the freeze as well as after it, and write down when each was taken.

## Observations

- New decisions in spec.md, each marked "confirm at review": the per-Worker panel's query carries the Task Queue filter; with `--by-identity` each history's line also reports a timeout on any Workflow Task and marks a failed Activity; each capture flood runs on a freshly started dev server.
- The helper needs no thread pool: 518 histories took 37.7 seconds.
- The Web UI's Task Queue page and Workers tab list both Workers with the same last-access second, so they do not name the frozen Worker.
- No rate above 10 receipts per second was tried again; the one slow run argues against raising it before the cause is known.
- The healthy small run's history timings and extra tool readings were not captured; that optional item stays open.
- `plan.md` and `todo.md` are still fully checked and not archived; the archive and the new plan come next.

## Suggested Skills for Next Session

- `temporal:temporal-developer`: the exercise 06 copies, the flood starter, and Worker identity in history.
- `python:python`: the 06 copies, the helper's `--by-identity` and `--summary` flags, and their tests.
- `content-design:style-linting`: every prose step.
- `content-design:tutorial-writing` and `voice:teaching`: the exercise 06 README, the fold-ins, and draft part 7.
