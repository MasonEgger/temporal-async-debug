# Session Summary: Goal Step 12, Part 7 Draft

**Date**: 2026-11-11
**Duration**: not tracked
**Conversation Turns**: no user prompts; goal-loop dispatches (implement, validator iteration 1, fix, validator iteration 2, fix, validator iteration 3, finalize)
**Estimated Cost**: not tracked
**Model**: orchestrator claude-fable-5-2; step executors (implement, fix passes, finalize) on "sonnet"; validators (three passes) on "opus", as the goal file directs

## Key Actions

- Wrote the seventh series draft, `docs/drafts/part-7-finding-the-frozen-worker.md` ("Finding the frozen Worker in a fleet"), the tutorial form of exercise 06.
  It runs 954 lines in 13 steps, with 38 quoted blocks (30 spliced from the exercise 06 README, 8 from code in the exercise 06 copies) and 9 images.
  It carries no CLAUDE_HELP tag.
- The draft teaches the fleet version of the diagnosis: two Workers on one Task Queue, the Event Histories name the frozen one, then the process tools run on that one process.
  It ends with the probe test and the thread-pool fix, and a rerun of the flood.
- Added a part 7 section to `docs/drafts/smell-reports.md` with the smell report and nine "Build decision:" lines.
- Checked the six Step 12 boxes in todo.md.
- Validator loop: iteration 1 returned block (4 block, 3 warn, 3 info); fix iteration 2; iteration 2 returned warn (1 warn, 3 info); fix iteration 3; iteration 3 returned clean (3 info).
  Step 12 used all three validator iterations.
- The four block findings were wrong part numbers in cross-references.
  Six references were corrected.
  The other iteration 1 findings, fixed in iteration 2, were a missing primer link, one misquoted hedge in the smell report, and three sentences over the 25-word cap.
- The iteration 2 warn was two pairs of fenced blocks back to back with no prose between them.
  Iteration 3 added two intro sentences.
- Final checks: keyboard lint exit 0; Vale on the draft shows 0 errors and 2 warnings, both `MasonBase.SentenceCapitalization` false positives (lines 384 and 641); `uv run pytest -q` 119 passed.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| `/goal @goal.md` loop, `Mode: implement` | Wrote the part 7 draft, the smell-report section, and the todo.md checks | Tree dirty with three paths |
| Validator, iteration 1 | Checked cross-references, blocks, and prose | block: 4 block, 3 warn, 3 info |
| Executor, `Mode: fix` | Corrected six part references, added the primer link, fixed the hedge and three long sentences | Tree dirty, tests green |
| Validator, iteration 2 | Re-checked the files | warn: 1 warn, 3 info |
| Executor, `Mode: fix` | Added two intro sentences between back-to-back blocks | Tree dirty, tests green |
| Validator, iteration 3 | Re-checked the files | clean: 3 info |
| Executor, `Mode: finalize` | Gates, session summary, lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: the draft runs 550 to 800 lines.
- Deviated: the draft runs 954 lines in 13 steps (running the healthy flood, reading the bad summary, grouping timeouts by Worker, seeing the identity in a history, reading the one process, comparing logs, checking the tools, reading the dashboard, taking the method to production, finding the call, writing the probe test, moving the lookup to a thread pool, rerunning the flood).
- Impact: the 38 quoted blocks, the tools table, and nine images carry the length.
  The prose is short.

- Plan said: quoted blocks come from the README or a `.masked` capture.
- Deviated: all 38 blocks come from the README or from the practice and solution copies, none from `.masked` files.
  The two probe-test excerpts come from `solution/tests/test_probe.py`.
  One command (`temporal workflow show ... --output json`) is a fenced block where the README has it inline.
- Impact: no capture file was read into the draft.

- Plan said: run content-design:review-content, which launches the copy-editor agent.
- Deviated: the agent cannot be launched from this context.
  Vale and a manual read replaced it.
- Impact: no copy-editor findings exist for part 7.

- Plan said: Vale target is 0 errors and 0 warnings.
- Deviated: two MasonBase.SentenceCapitalization warnings survive many rewordings.
  One sits on the possessive in the quoted TODO PART C comment of the practice file, which cannot change.
  The other moves to a different line on each edit and lands inside a quoted block.
  Fixes that worked in prose: remove backticks from PID@host identities, reword possessives, avoid the word "shows" and `--summary` in prose.
- Impact: report the two warnings to the owner as the same false-positive class the exercise 06 README carries.

- Plan said: copy the README's tools table.
- Deviated: five possessives in the table were reworded, with no change of fact.
- Impact: none beyond wording.

- Plan said: TODO cross-links for part 6 and the primer.
- Deviated: the draft refers to the root README section on blocked event loops (as the README does) and adds a TODO cross-link for it.
  It does not refer to the primer in that place.
- Impact: Step 14 can fill in the link.

- Plan said: a TODO cross-link for the primer.
- Deviated: the Introduction uses a relative link to event-loop-primer.md, in the form part 1 uses.
- Impact: no link to fill in for the primer in Step 14.

- Plan said: part numbers follow the series order, where exercise N is part N+1.
- Deviated: the implement pass took "exercise N" as "part N".
  The fix pass corrected six references that named the wrong part (the exercise-to-part mapping was missing from the implement prompt, an orchestrator gap) and split three sentences that were over the 25-word cap.
- Impact: the cross-references now match the series; the draft grew from 945 to 949 lines.

- Plan said: use the code sandwich for every block.
- Deviated: the first draft left two pairs of blocks in Step 13 back to back; the third pass added an intro sentence before the second block of each pair.
- Impact: Step 12 used all three validator iterations.

## Efficiency Insights

**What went well:**
- The validators checked cross-references against the series order, which found the wrong part numbers.
- Vale plus a manual read covered the review pass when the copy-editor agent was unavailable.
- Splicing quoted blocks from the exercise 06 README kept the draft's facts tied to captures.

**What could improve:**
- The implement prompt did not state the exercise-to-part mapping, so four block findings came from one missing sentence.
- The code-sandwich rule was not in the implement prompt, and no script scanned for back-to-back blocks before the validator ran.
- The draft ended 154 lines over the planned range.

**Course corrections:**
- Both prompt gaps were the orchestrator's, not the executor's.
  They cost two fix passes and all three validator iterations.

## Process Improvements

- State the exercise-to-part mapping (part 1 is the healthy Worker with no exercise; part N+1 is exercise N) in any prompt that writes or edits a series draft.
- Put the code-sandwich rule in the prose prompt and run a script for adjacent fenced blocks before dispatching the validator.
- Pre-check replacement sentences with Vale on a full scratch copy of the real file under the same directory layout, since a small scratch file with fenced blocks gives spurious warnings.

## Observations

These are build decisions for the owner to confirm at review.

- The nine "Build decision:" lines in the part 7 section of `docs/drafts/smell-reports.md`.
- The draft length: 954 lines against the 550 to 800 planned.
- Tooling limits: the copy-editor agent could not be launched from the executor, so Vale plus a manual read stood in for the review-content pass.
  The validator sessions could not load the Temporal docs MCP, so the orchestrator ran the docs checks and passed the results into the dispatches.
  The validator did not invoke the content-design or voice skills as skills.
- Left for Step 13 on purpose: the wording "In parts 1 to 6" at draft lines 6 and 189 is not strictly true of every part.
- Info findings left as they are: `MasonBase.SentenceCapitalization` at lines 384 and 641, both inside quoted blocks.

## Suggested Skills for Next Session

- `content-design:tutorial-writing`: Step 13 updates parts 1 to 6, which are step-by-step tutorials.
- `voice:teaching`: Mason's register on top of the tutorial canon.
- `content-design:review-content`: the updated prose goes through Vale and the review pass.
- `temporal:temporal-developer`: the updates make claims about Workers, identities, and history events.
