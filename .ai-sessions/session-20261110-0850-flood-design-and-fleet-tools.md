# Session Summary: Flood Design And Fleet Tools

**Date**: 2026-11-10
**Duration**: an evening and the next morning; active time not tracked
**Conversation Turns**: about 4 user turns
**Estimated Cost**: not tracked; the session crossed several context summaries
**Model**: claude-fable-5-2

## Key Actions

- Answered Mason's question about whether the lessons still teach once a second Worker is in the picture, and recorded the ruling: exercises 01 to 05 stay on one Worker with a teaching-code note, and exercise 06 is the realistic case.
- Ran three scratch spikes outside the repository.
  The first checked every tool the series teaches against two Workers, at eight receipts and under a flood.
  The second was a design matrix for exercise 06's flood: bursts and steady traffic, two and four Workers, two and 100 Activity slots, ending in six freeze runs and one healthy run of the chosen design.
  The third ran exercise 03's solution copy eight times on one and two Workers.
- Rewrote the exercise 06 design in spec.md around a flood of 10 receipts per second on two Workers at the SDK's default slot counts, with a healthy flood as the rate check.
- Wrote the fleet tool results into spec.md as a "The tools in a fleet" block, and moved the per-Worker Grafana panel and a third Prometheus target out of Deferred.
- Wrote exercise 03's second-Worker step from the spike: `--bad 2` on one Worker, then `--bad 4` on two.
- Added the design principle "Loud first, then realistic.", a non-goal (no load test or benchmark), and a Deferred entry for a bigger flood.
- Added the ruling and the spikes to the Decisions list of the field evidence summary.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| What changes overall, and do the lessons still teach? | Compared the single-Worker captures with the two-Worker spike | Lessons hold on one Worker; the open point was how to frame a fleet |
| Keep one Worker early, show the real world in 06, check the tools in a fleet, flood it if needed | Ran the three spikes, then edited spec.md | Spec is decision-complete for the reworked exercise 06 and the fold-ins |
| "Wait what? Are you ok" | Explained the context summary pause | Work continued with nothing lost |
| Are you replying to my previous message about the risks? | Checked the transcript; the two risks were exercise 03's placement and exercise 06's quiet symptom | Confirmed, and mapped each risk to its spec change |

## Efficiency Insights

**What went well:**
- The design matrix ran before any exercise code, so the choice of steady traffic over a burst cost scratch runs only.
- A healthy flood at the same rate gave a control: 0 of 521 receipts failed, so the failures in the freeze runs belong to the bug and not to the load.
- Six freeze runs gave ranges to quote in place of single figures.

**What could improve:**
- The edit script had an insert and a replace that met at one line boundary, and it stripped the blank line before a new paragraph; both were caught by its own checks, but only after a first failed run.
- Vale flagged two phrasings in the new text after the edit; linting the new text before applying it would have saved a pass.
- The after-fix flood was not measured, so the spec carries it as an assumption.

**Course corrections:**
- Exercise 06 moved from eight receipts to a flood: at eight receipts and two Activity slots nothing fails, and at default slots under steady traffic 3.3 to 4.3 percent of receipts fail.
- A burst of 500 was dropped as the load shape, because it overloads the healthy Worker and hides the effect.
- Four Workers at 30 receipts per second was discarded as machine overload, not a finding.

## Process Improvements

- For a fleet exercise, vary slot counts and load shape in the spike before fixing either in the spec.
- Run a healthy control at the same load for every freeze measurement.
- Lint new spec text with Vale before the scripted edit, not after.

## Observations

- With a healthy Worker on the queue, `temporal task-queue describe` reads a backlog of 0 through the freeze.
- The frozen Worker's `WorkflowWorker` slots-used gauge climbs toward 100 while the healthy Worker's stays at 0 to 2; the `ActivityWorker` gauge does not separate them.
- Every Workflow Task timeout in the freeze runs traced to the frozen Worker's identity (77 to 84 per run).
- Only the frozen Worker logs "Task not found when completing" and `TMPRL1104` at the thaw; `TMPRL1101` appeared in no run.
- New Vale alerts in spec.md's Starting context come from the owner's verbatim quotes and stay as they are.
- `plan.md` and `todo.md` are still fully checked and not archived, so `/bpe:plan` refuses until they are archived.

## Suggested Skills for Next Session

- `python:python`: the exercise 06 copies, the flood starter's pure plan and summary functions, and the `--by-identity` and `--summary` helper changes.
- `temporal:temporal-developer`: the two-Worker flood capture, Worker identity in history, and the per-Worker slot gauge.
- `content-design:tutorial-writing` and `voice:teaching`: the teaching-code note, the single-Worker sentence, "The tools in a fleet", and the 06 README.
- `content-design:style-linting`: every prose step.
