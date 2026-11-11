# Session Summary: Goal Step 11, Fold-Ins for Exercises 01 to 05

**Date**: 2026-11-11
**Duration**: not tracked
**Conversation Turns**: no user prompts; goal-loop dispatches (implement, validator iteration 1, fix, resumed fix, validator iteration 2, finalize)
**Estimated Cost**: not tracked
**Model**: orchestrator claude-fable-5-2; step executors (implement, fix passes, finalize) on claude-sonnet-5-5; validators (two passes) on claude-opus-5-5

## Key Actions

- Folded the exercise 06 findings into the five exercise READMEs.
  Each one gained a sentence after the "During this exercise, you will" list saying the exercise runs one Worker with two Activity slots so the failure is loud, and that exercise 06 shows the same bug on a fleet.
  Each Part B now starts with a link to the root README's recognition block.
- Exercise 01: added a "same bug, other library" table at the end of Part C (categories and call shapes; a package is named only where its name is not also a company name; the LLM-client row is generic).
  Added a Part D statement that `activity_executor` runs only `def` Activities, so an `async def` Activity stays on the event loop whatever executor the Worker has.
- Exercise 02: added the heartbeat sentence in Part C (a heartbeat call inside a blocked loop is not sent until the loop runs again).
  Part E's starter output and receipts block now come from the newer solution capture, and the prose says which blocks come from which capture.
- Exercise 03: moved the second Worker out of the optional section into Part E's main path, framed as GIL isolation and not as fleet sizing.
  The one-Worker step runs `--bad 2` and the two-Worker step runs `--bad 4`; no `--bad 3` remains.
  Timings and placement counts are quoted from one capture per step, with a sentence that the figures depend on the reader's CPU.
  The `py-spy` and busy `top` blocks in Parts B and E were replaced from retakes, and the prose says so.
- Exercise 05: one sentence explains why the Workflow Task panels are near empty (a stall of about 350 ms on a 30-second rate average); the images stay.
- Privacy masking across the five READMEs: identities read `PID@host`, public addresses read `<ip>`, place names read `<city>`, home paths read `<repo>` and `<home>`, and each README has one disclosure sentence at its first placeholder block.
  Only the private token is replaced; everything else on a captured line stays.
  The `top` USER column stays as captured.
- Checked todo.md Step 11.
- Validator loop: iteration 1 found one block and ten warn findings; a fix pass and a resumed fix pass followed; iteration 2 returned "clean".
- Final checks: `just lint-prose` on the five files shows 0 errors and the same warning counts as before the step (2, 4, 2, 3, 3, all `MasonBase.SentenceCapitalization`, the known false-positive class).
  `just lint-keyboard` exit 0; `uv run pytest -q` 119 passed.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| `/goal @goal.md` loop, `Mode: implement` | Edited five exercise READMEs and checked todo.md Step 11 | Tree dirty with six paths |
| Validator, iteration 1 | Checked prose and blocks against captures | block: one block, ten warn |
| Executor, `Mode: fix` | Applied the findings | Tree dirty, tests green |
| Executor, `Mode: fix` (resumed) | Replaced three sentences that raised new Vale warnings | Tree dirty, warnings cleared |
| Validator, iteration 2 | Re-checked the files | clean |
| Executor, `Mode: finalize` | Gates, session summary, lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: nothing about masking captured output in the five READMEs.
- Deviated: the orchestrator added privacy masking as a build decision, for the owner to confirm at review.
- Impact: captured blocks no longer carry the capture machine's address, place name, hostname, or home paths.
  Earlier commits still hold the unmasked text; whether history needs a rewrite is the owner's call.

- The exercise 03 digest suffix stays as captured.
  It is a hash of the location text, so it is derived from the masked place name.
  Listed for the owner at review.

- Plan said: run the copy-editor agent through content-design:review-content.
- Deviated: the agent tool is not available in this context, so the review ran as Vale (`lint-prose`), the keyboard check, a banned-word grep, and a manual read of the added prose.
- Impact: no agent findings; the owner reviews once after the build.

- The Temporal docs MCP is not reachable from the executor or the validator.
  The orchestrator ran the docs queries and passed the results in.
  The validator did not load the section's skills separately.

- Plan said: exercise 02, replace the starter block and receipts block if the command matches.
- Deviated: none. The command matches (`--bad 1 --geo 1 --rollups 1 --receipts 2`, per INDEX.md), so both blocks were replaced with splices from the solution-fleet masked files, and the image alt text and sentences were rewritten.
- Impact: starter output, receipts, and image are one run.

- Plan said: exercise 03 py-spy solution blocks, replace the MainThread block.
- Deviated: the pool-thread (`ThreadPoolExecutor-0_0`) block was also replaced with the full stack from the same pyspy-solution-fixed file, so the PIDs in both blocks match.
  The practice and solution `top` blocks beside the py-spy blocks were replaced with top-1 of each retake.
  The idle `top` block (0.0 percent) has no retake file and stays from the old capture.
- Impact: the idle reading and the retake readings come from different runs.

- Exercise 02 Part E and exercise 03 Parts B and E now quote two captures each.
  The fix pass added sentences that say which block comes from which capture.
  The exercise 03 idle `top` block and `asyncio ps` block stay from the older capture.

- Plan said: disclosure sentence in the form of the exercise 06 sentence.
- Deviated: the sentence ends "that appear in your own output" instead of "that your own output shows", because Vale mis-segments the rest of the file after a sentence ending in "shows" and raises extra SentenceCapitalization warnings.
- Impact: none for the reader. In exercise 04 Vale still reports 3 SentenceCapitalization warnings (the baseline count), but one is attributed to the disclosure line; it is the same possessive false-positive class relocated by the segmenter.

- Plan said: exercise 05, add a matching sentence beside the second image if it does not say why.
- Deviated: left the second image text alone; it already says the fleet ran too short a time to draw a point.
- Impact: none.

- The step took two validator iterations.
  Iteration 1 found one block and ten warn findings, most traceable to gaps in the orchestrator's masking instructions: whole location values were replaced so suffixes were lost, place names were missed in two block types, and replaced blocks were not disclosed as a different capture.
  The fix pass was resumed once because three sentences the orchestrator supplied verbatim raised three new Vale warnings (two WordList hits on "above", one sentence over 25 words); the corrected text cleared them before validator iteration 2.

- The exercise 01 table names three Python packages and keeps the LLM-client row generic.

## Efficiency Insights

**What went well:**
- The validators diffed quoted blocks against the captures, which found the lost suffixes and counts.
- Vale plus a manual read covered the review pass when the copy-editor agent was unavailable.

**What could improve:**
- The masking instruction said "mask the location" and did not say to keep the rest of the line.
- Replaced blocks were not disclosed as coming from a different capture until the validator asked.
- Orchestrator-written sentences went to the executor without a Vale run.

**Course corrections:**
- The masking gaps and the three new warnings came from the orchestrator's instructions, not the executor.
  They cost one fix pass and one resumed fix pass.

## Process Improvements

- State a masking rule as "replace only the private token, keep every other character of the line".
- Say at the block which capture it comes from when a section mixes two.
- Run Vale on replacement sentences before passing them to an executor as verbatim text.

## Observations

These are build decisions for the owner to confirm at review.

- The privacy masking and the exercise 03 digest suffix, described under Deviations.
- Exercise 03's second Worker is part of the main path and is framed as GIL isolation.
- Info findings left as they are: `MasonBase.SentenceCapitalization` on the exercise 04 disclosure sentence (line 74, a list of code spans at the start, the known false-positive class), and `MasonBase.FirstUse` suggestions on LLM, GIL, and PID in exercises 01 and 03.

## Suggested Skills for Next Session

- `content-design:tutorial-writing`: the next plan step continues the exercise and draft prose.
- `voice:teaching`: Mason's register on top of the tutorial canon.
- `content-design:style-linting`: the prose goes through Vale before it is committed.
- `temporal:temporal-developer`: the fold-ins make claims about Workers, identities, and history events.
