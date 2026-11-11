# Session Summary: Goal Step 10, Exercise 06 README

**Date**: 2026-11-11
**Duration**: not tracked
**Conversation Turns**: no user prompts; seven goal-loop dispatches (implement, validator iteration 1, fix, validator iteration 2, fix, validator iteration 3, finalize)
**Estimated Cost**: not tracked
**Model**: orchestrator claude-fable-5-2; step executors (implement, two fix passes, finalize) on claude-sonnet-5-5; validators (three passes) on claude-opus-5-5

## Key Actions

- Wrote `exercises/06-finding-the-frozen-worker/README.md` (903 lines) in the house exercise structure.
  It has Parts A to E, practice TODO letters C and D, 23 quoted blocks taken from masked captures and repository files, nine embedded panel images, a tools-in-a-fleet table, and a production note on Worker identity.
- Added the exercise 06 section to `docs/drafts/smell-reports.md`.
- Checked todo.md Step 10.
- Validator loop: iteration 1 "warn" (nine warn, seven info), fix; iteration 2 "warn" (three warn, three info), fix; iteration 3 "clean" (three info, all the known `MasonBase.SentenceCapitalization` false positives).
  The step used the full iteration budget.
- Final checks: `just lint-prose` on the README gave 0 errors, 3 warnings (the three false positives), 14 suggestions.
  `smell-reports.md` gave 0 errors, 83 warnings, 14 suggestions, all in rule classes the file already had (79 and 11 before the step).
  `just lint-keyboard` exit 0; `uv run pytest -q` 119 passed.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| `/goal @goal.md` loop, `Mode: implement` | Wrote the README, the smell-report section, and the todo check | Tree dirty with three paths |
| Validator, iteration 1 | Checked prose against captures and repository files | warn: nine warn, seven info |
| Executor, `Mode: fix` (iteration 1) | Applied the findings | Tree dirty, tests green |
| Validator, iteration 2 | Re-checked the files | warn: three warn, three info |
| Executor, `Mode: fix` (iteration 2) | Applied the findings | Tree dirty, tests green |
| Validator, iteration 3 | Re-checked the files | clean, three info |
| Executor, `Mode: finalize` | Gates, session summary, lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: the bad flood's failures stop before the freeze does, and the fleet looks recovered.
- Deviated: the README reports flood B run 4 as captured.
  Failures stop at +10s, 20 seconds before the thaw, but every bucket to +45s is still slow (slowest 38.65 s).
  The README does not use the "fleet looks recovered" framing.
- Impact: the README does not say the fleet looks recovered.

- Plan said: the Task Queue page does not separate the Workers; the backlog reads 0 in each single read.
- Deviated: the README reports each pass as captured: a 39-task backlog aged 3.5 s and pollers 6 and 8 s stale at the last pass only.
- Impact: the tools table rates describe and the Web UI as separating the Workers only at the last reading.

- Plan said: take the starter commands from the capture index.
- Deviated: the index records `<flags>` only.
  The README shows `--bad 0` for flood A and the defaults for the bad flood, and lists the defaults from argparse.
- Impact: the commands match the capture counts but are inferred.

- Plan said: Part B runs the process tools after the histories name the PID.
- Deviated: the process readings are mid-freeze readings from the same capture; Step 3 tells the reader to rerun the flood and confirm the match afterward.
- Impact: the order of work is stated as the incident order.

- Plan said: raw files win over INDEX/FINDINGS.
- Deviated: FINDINGS lists the last-pass metrics times as 35.1 ms (frozen) and 2.8 ms (healthy); the raw files read 2.8 ms on port 9464 (frozen) and 35.1 ms on 9466 (healthy).
  The README uses the raw order.
- Impact: none beyond the swap.

- Plan said: Web UI rows from the rendered pages.
- Deviated: only API JSON was saved; the row says so and carries a help tag for the owner.
- Impact: no Web UI screen is described.

- Plan said: the bad run's identity is shown in a history.
- Deviated: the JSON history has no masked copy, so the README states the identity from the JSON and quotes no block (help tag).
- Impact: one reader command (`--output json`) is not from the repository.

- Plan said: run `content-design:review-content` with the copy-editor agent.
- Deviated: the agent could not be launched; Vale, the keyboard lint, a manual checklist, and the validator's prose review replaced it.
- Impact: no copy-editor findings.

- Plan said: image readings come from the capture index.
- Deviated: the index lists windows only; the readings come from opening the PNG files.
  The solution latency panel reads about 7 to 17 ms, where FINDINGS says 6 to 17.
- Impact: none beyond the one figure.

- Plan said: nothing about restarting servers before a flood.
- Deviated: the fix passes added a reader instruction to restart the dev server and both Workers before each flood.
  It matches how the captures ran.
- Impact: the reader's run starts from the same state as the captures.

- Plan said: the Temporal docs checks happen in the step.
- Deviated: the orchestrator ran the docs queries (Worker identity, Started events) itself, because executors and validators cannot reach the docs MCP.
  The iteration 2 and 3 validators relied on those results.
- Impact: the claims rest on the docs pages and the installed SDK source.

- Plan said: back each tool-table claim with a capture.
- Deviated: the note that `py-spy` in a pod needs `SYS_PTRACE` rests on the py-spy project's own documentation, not on a capture.
- Impact: the owner may want to confirm it at review.

- Plan said: nothing about help tags.
- Deviated: two `<CLAUDE_HELP>` tag pairs stay in the README for the owner.
  One marks that no masked JSON excerpt shows the bad run's Worker identity; the other marks that the Web UI table row rests on saved API JSON, not rendered pages.
- Impact: the owner resolves both at review.

## Efficiency Insights

**What went well:**
- The validators checked quoted blocks, figures, and claims against the captures and the SDK source, and each pass found fewer problems (nine warn, then three, then none).
- The raw-file-wins rule caught the swapped metrics times in FINDINGS.

**What could improve:**
- The step used all three validator iterations.
  Two of the problems in iteration 3 came from the iteration 2 fix prompt, not from the executor.
- A setup rule stated once at the top of a part was missed at the second flood.

**Course corrections:**
- These were the orchestrator's errors.
  The iteration 2 fix prompt passed on a narrowed claim ("none of the tools from exercises 1 to 5 names the stuck Worker by itself") without checking it against the README's own tools table, where `py-spy dump` rates "Yes."
- The same prompt gave a two-cause explanation of a line-number difference whose arithmetic did not add up.
  A third cause, two dropped comment lines, was missing.
- Both cost a third validator pass.

## Process Improvements

- Check a reviewer's suggested wording against the document's own tables before sending it to a fix pass.
- When prose explains a line-number difference between two copies of a file, run `diff` and make the arithmetic add up in the text.
- Put a setup rule at the step where the reader acts on it.
- Plan the docs MCP checks as orchestrator work for any step that needs them.

## Observations

These are build decisions for the owner to confirm at review.

- The README reports each flood as one run and follows the capture wherever it disagrees with spec.md.
- The smell-report section for exercise 06 lists the build decisions.

## Suggested Skills for Next Session

- `content-design:tutorial-writing`: Step 11 folds the exercise 06 findings into the exercise 01 to 05 READMEs.
- `voice:teaching`: Mason's register on top of the tutorial canon.
- `content-design:style-linting`: the prose goes through Vale before it is committed.
- `temporal:temporal-developer`: the fold-ins make claims about Workers, identities, and history events.
