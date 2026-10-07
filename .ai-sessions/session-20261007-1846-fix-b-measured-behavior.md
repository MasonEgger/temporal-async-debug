# Session Summary: Correct the Spec and CLAUDE.md to Measured Behavior

**Date**: 2026-10-07
**Duration**: One docs-only correction pass outside the plan (implement, three validator iterations with two fix rounds, finalize)
**Conversation Turns**: Orchestrated; one implement dispatch, two fix dispatches, three validator dispatches, one finalize dispatch
**Estimated Cost**: Moderate; four prose files re-grounded against live capture files, no code changed
**Model**: Implementer Opus 5.5; validator Fable 5.1 (clean at iteration 3); finalize Opus 5.5

## Key Actions

- A seven-agent adversarial review plus three live re-runs showed spec.md and CLAUDE.md carried claims that live behavior refuted.
  Two of them were introduced while correcting an earlier error.
- Starved bystanders: the server labels a never-started activity ScheduleToStart, not schedule_to_close, because it copies schedule_to_close into schedule_to_start when the latter is unset.
- Poller LastAccessTime: the pollers live in the Rust core and keep long-polling through a freeze.
  The age grows only while no activity permit is free, and the worker never left the Pollers list, so LastAccessTime is not a freeze signal and only a weak saturation hint.
- slots_available reads 0 in both a freeze and saturation while both slots are held, so it does not tell them apart.
- maximum_attempts=1 is set only on the geo activities; the rollup's failure chain depends on the default policy's second attempt.
  The antipattern's real lesson is at-most-one dispatch, not exactly-once: keep retries and make the activity idempotent.
- The deterministic freeze lesson is now stated as measured: the rollup fails ScheduleToClose caused by StartToClose, the healthy geo is awaited before the bad run, and the instant bystanders are gated on the bad run's second activity STARTED and stall through the final freeze (8 of 8 runs, reverify4).
- The saturation section scopes the ScheduleToStart label to receipts, rollup, and quote, and states the healthy geo completes late (about 60s, reverify2 59.88s) on its 150s schedule_to_close.
- The latency metric is described as a lagging confirmation (reverify2: 3464 to 63530 ms for slow, 63530 to 63543 ms for slow-heartbeat); backlog age is the live tell.
- The scrape figure is "a few milliseconds" (reverify4: 0.7 to 1.7 ms), replacing a blanket "sub-millisecond".
- spec.md now carries the two-tool asyncio ps / py-spy story with current line numbers (activities.py:142 and :148 under :196 and :225, worker.py:124, pstree rollup.py:48).
- A banned word and multi-sentence lines were fixed across the four files.
- `just check` green: 128 passed.

## Deviations from Plan

- Plan said: docs-only correction pass on spec.md, CLAUDE.md, plan.md, todo.md against the reverify captures.
- Deviated: plan.md also had "a couple of seconds" (Step 3 NOTE, now "a few seconds"), "a price quote goes stale" (Step 4 NOTE, now "a late price quote is out of date"), and a Step 9 MCP hint asserting the poller LastAccessTime "goes stale" (now "how the poller LastAccessTime behaves"), all reworded so the verify grep is clean; step semantics unchanged.
- Deviated: the Step 9 heading rename to "Full README Catalog" was applied in plan.md (index and section heading) and both todo.md occurrences, not only todo.md:98.
- Iteration 1 fix (validator findings, re-grounded on scratchpad reverify4 after commits 6e4e433 and e4ab39c moved the starter gate to the bad run's get_location STARTED plus 1s): the receipt/quote stall-and-complete-at-thaw claim is now captured (reverify4: 19/19 receipts and quotes COMPLETED, executionDuration 28.85-29.12s, first workflow task +1.03 to +1.26s after get_location STARTED, 8/8 runs, including 3 blockq runs, so the quote case is no longer inferred); spec.md, CLAUDE.md, and plan.md Step 7 now describe the second-activity gate and why (the thaw between the two freezes; 1 of 16 bystanders failed with a get_ip gate).
- Deviated: the healthy geo in the freeze path is now stated to survive by ordering (awaited, under 1s, 8/8), not by its 120s start_to_close; the saturation section scopes the ScheduleToStart label to receipts, rollup, and quote and states the healthy geo completes late (~60s, reverify2 59.88s) on its 150s schedule_to_close.
- Deviated: the poller prose now says LastAccessTime is not a freeze signal at all (ages 7s/19s/7-9s at t+8/t+20/t+40, inside the idle 0-59s cycle) and only a weak saturation hint; the latency figures are replaced with reverify2's 3464 -> 63530 ms (slow) and 63530 -> 63543 ms (slow-heartbeat); the scrape figure is "a few milliseconds" (reverify4: 0.7-1.7 ms); py-spy lines activities.py:142/:148 under :196/:225, worker.py:124, and pstree rollup.py:48 added to spec.md.
- Deviated: plan.md Step 9 and Step 10 dropped "poller going stale" and "stale poller"; todo.md Step 9 line now names backlog age the tell and the latency metric a lagging confirmation.
  CLAUDE.md's maximum_attempts=1 bullet folded into the workflow.py bullet (info finding).
- Still from summary, not re-read: the 75-second Pollers-list observation (kept from the prior spec text and the orchestrator's summary) and the slow-12 ScheduleToClose flip.
- Impact: none on code; just check green (128 passed).
- Iteration 2 fix (truth.overstated-claim): the single-run thaw figure (reverify3 blockq-1, 138 ms) is replaced in spec.md (poller paragraph, block scenario bullet, gate rationale), CLAUDE.md:82, and plan.md:335 with the reverify4 range "60 to 570 ms across the 8 final runs, depending on get_ip's HTTP call" plus "138 ms in the run that exposed the race".
  The spec.md poller parenthetical "the pollers re-poll once in the thaw" is split: the activity poller re-polls in the thaw, the workflow poller re-polls when the next workflow task is dispatched to it, even mid-freeze (1.3 s into the second freeze for the receipts' workflow task), and that mid-freeze re-poll is now cited as the evidence for long-polling through a freeze.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Fix B implement dispatch | Re-grounded spec.md, CLAUDE.md, plan.md, todo.md against the reverify captures | Docs corrected; validator iteration 1 flagged uncaptured and overstated claims |
| Fix dispatch, iteration 1 | Re-grounded on reverify4 after the e4ab39c gate change; captured the receipt/quote thaw, healthy geo ordering, poller and latency figures | Validator iteration 2 flagged a single-run thaw figure |
| Fix dispatch, iteration 2 | Replaced the single-run figure with the 8-run range; split the poller re-poll claim | Validator Fable 5.1 clean at iteration 3 |
| Finalize dispatch | `just check`, session summary, lesson, commit, push | One signed commit on scaffold |

## Efficiency Insights

**What went well:**
- Quoting the capture file (reverify2, reverify3, reverify4) next to every figure made each validator finding checkable and each fix verifiable with grep.

**What could improve:**
- Two claims were "corrected" in an earlier pass from reasoning rather than a fresh capture, and both were wrong; a re-run after 6e4e433 and e4ab39c would have caught them before review.
- The first fix round still carried a single-run figure (138 ms) stated as typical, which cost a third validator iteration.

**Course corrections:**
- After e4ab39c moved the gate to get_location STARTED, the corrections were re-grounded on reverify4 instead of the earlier captures.

## Process Improvements

- After any code change a spec claim depends on, re-run the scenario and re-capture before editing the claim, and cite the capture file in the spec record.
- State a measured figure as a range over the runs taken, with the run count, never a single run's value.

## Observations

- The review found that the design authority itself had drifted from live behavior, so the code was right and the docs taught the wrong signals (stale poller, slots_available as a discriminator).
- Two claims were still taken from a summary rather than re-read: the 75-second Pollers-list observation and the slow-12 ScheduleToClose flip.
  They are candidates for the next capture.

## Suggested Skills for Next Session

- `temporal:temporal-developer`: any further claim about timeout labels, pollers, or retry policy should be checked against the SDK and docs.
- `content-design:review-content`: README.md still says the poller LastAccessTime goes stale during a freeze and during saturation (lines 255, 402, 550) and needs the same correction pass.
- `python:python`: if the next step touches starter.py or the activities.
