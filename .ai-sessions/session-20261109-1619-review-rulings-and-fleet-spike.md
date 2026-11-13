# Session Summary: Review Rulings And The Two-Worker Spike

**Date**: 2026-11-09
**Duration**: about 3 hours
**Conversation Turns**: about 8 user turns
**Estimated Cost**: not tracked; the session crossed several context summaries
**Model**: claude-fable-5-2

## Key Actions

- Reviewed the fleet-localization spec commit and the field evidence summary, and listed what the review left open.
- Rewrote the `scaffold` branch history to remove detail that the Privacy rule forbids, and force-pushed it.
- Asked Mason four questions and recorded the rulings: widen the Privacy rule, one shared recognition block, four fold-ins, no reorder, and the production canary deferred.
- Ran a scratch spike of exercise 06's design outside the repository: two Workers on one Task Queue, a `sqlite3` lock wait as the blocker, five freeze runs and one healthy run.
- Rewrote the exercise 06 requirements in spec.md from the spike results, replacing three capture assumptions.
- Wrote the rulings into spec.md (Privacy invariant, Deferred, Design principles, exercises 01 to 03, the recognition block, counts and the documentation tree), widened the Privacy paragraph in CLAUDE.md, and closed the open decisions in the research summary.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Review the other agent's commit and say what we should do | Read the commits, the spec phase, and the research summary | Recommendations and a list of open rulings |
| Purge the internal detail first, force push as needed | Rewrote the branch history and force-pushed `scaffold` | Branch clean; the Privacy rule widened afterward |
| Ask the questions you need, through AskUserQuestion | Asked four questions | Four rulings recorded |
| Continue without further questions | Ran the two-Worker spike, then edited spec.md, CLAUDE.md, and the research file | Spec is decision-complete for the fleet-localization phase |

## Efficiency Insights

**What went well:**
- The spike ran before the plan was written, so the wrong capture assumptions cost one spec edit and no rework in code or prose.
- One script with asserted line prefixes and match counts applied about 25 spec edits in a single pass, and it would have stopped on any drift.
- Five runs gave counts to quote, which keeps "always" out of the spec.

**What could improve:**
- The first spike runs used two rollups, which added slot noise; the rollup count should have been a variable from run 1.
- A `pkill -f` pattern matched its own shell and killed it.
- Two older lessons lived only in the Recent list of lessons.md, so the cap would have dropped them; they are now filed under Documentation.

**Course corrections:**
- Exercise 06 no longer promises a failed rollup: with a second Worker nothing fails, and the lesson is a partial, uneven stall.
- The localization signal moved from the bad run's first Workflow Task to the identity before each timeout and on the bad run's `get_location`.
- The recognition block claims a clean healthy log only after a fresh healthy-only capture, because an older baseline log could not be tied to healthy runs alone.

## Process Improvements

- Spike any exercise whose symptom depends on fleet behavior before writing its capture requirements.
- When a spike has a tunable that touches an invariant (here, the rollup count and slot noise), vary it from the first run.
- When the Recent list overflows, confirm each dropped lesson exists under a category first.

## Observations

- A frozen Worker's Rust-core pollers keep taking tasks, so in every run it took four of eight first Workflow Tasks.
- The server writes no history events for intermediate Workflow Task retries; the next scheduled event carries `attempt` 2 or 3.
- Sticky affinity stalls a Workflow whose Activity ran on the healthy Worker.
- The inherited starter gate scrapes one metrics port and fails open with two Workers.
- `plan.md` and `todo.md` are fully checked and not archived, so `/bpe:plan` refuses until they are archived.

## Suggested Skills for Next Session

- `python:python`: the exercise 06 copies, `db_lock.py`, the server-side gate, and the `--by-identity` helper change.
- `temporal:temporal-developer`: the two-Worker capture, Worker identity, and Workflow Task retry attempts in history.
- `content-design:tutorial-writing` and `voice:teaching`: the recognition block, the fold-ins, the 06 README, and draft part 7.
- `content-design:style-linting`: every prose step.
