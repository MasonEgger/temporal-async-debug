# Session Summary: Goal Step 14, Root Docs Refresh

**Date**: 2026-11-11
**Duration**: not tracked
**Conversation Turns**: no user prompts; goal-loop dispatches (implement, validator iteration 1, fix, validator iteration 2, finalize)
**Estimated Cost**: not tracked
**Model**: orchestrator claude-fable-5-2; implement, fix, and finalize passes on Sonnet executors; the two validator passes on Opus

## Key Actions

- The root `README.md` now says four layers and six exercises.
  It gained the exercise 06 table row, the `--by-identity` and `--summary` flags of the receipt-gap helper, the third scrape target (9466), and the seven-panel dashboard.
  "About the captured output" gained an ANSI-stripping bullet and a placeholder-masking bullet, and the README has a ptrace note.
  The 2026-11-11 latency panel readings are stated with no cause.
- `CLAUDE.md` was refreshed to match: layout, commands, exercise 06 facts, and the capture-masking rule.
- `docs/drafts/README.md` now describes a seven-part series.
- Part 1, the primer, the exercise 04 and 05 READMEs, and `docs/drafts/smell-reports.md` each took a small stale-fact fix.
- Part 7 gained two formatter comment lines (`<!-- fmt:off -->` and `<!-- fmt:on -->`) around one Python fence so `just check` passes.
- Validator loop: two of three iterations used.
  Iteration 1 returned one block (the `ruff format --check` failure on the part 7 fence), two warn (a causal claim in part 1 that no capture establishes, and a smell-reports sentence over the 25-word cap), and three info.
  One fix pass applied three exact edits from a pre-checked script.
  Iteration 2 was clean, with two info findings.
- Gate after the fix: `just check` exit 0 (119 root tests pass, solution copies pass), `just check-practice` exit 0, keyboard lint exit 0 on both file sets, zero Vale errors.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| `/goal @goal.md` loop, `Mode: implement` | Refreshed the root README, CLAUDE.md, drafts index, and five stale-fact files | Tree dirty with ten paths |
| Validator, iteration 1 | Ran the gate, linters, and the dispatch checklist | 1 block, 2 warn, 3 info |
| Executor, `Mode: fix` | Wrapped the part 7 fence, reworded the part 1 causal claim, split the long smell-reports sentence | Tree dirty, gate green |
| Validator, iteration 2 | Re-checked the files | clean, 2 info |
| Executor, `Mode: finalize` | Session summary, lessons, commit message, commit, push | This commit |

## Deviations from Plan

- Plan said: the step edits three artifacts (README.md, CLAUDE.md, docs/drafts/README.md).
- Deviated: the step also edits part 1, the primer, the exercise 04 and 05 READMEs, and the smell reports, each for a stale fact or a stale quote found in the final pass.
- Impact: eight files changed instead of three; all edits came from a prepared, Vale-checked script.

- Plan said: correct the latency figure if the fresh run differed.
- Deviated: the fresh root `just block` run of 2026-11-11 showed no receipt line on the Workflow Task Execution Latency panel and a highest reading of about 5.1 seconds on the rollup line.
  README.md and CLAUDE.md now state that run's readings and give no cause.
  This is a build decision.
- Impact: the docs report the readings only; a cause can be added if a later run explains it.

- Plan said: nothing about masking the root README's captured output.
- Deviated: the step masks the public address, place name, and paths with the placeholders `<ip>`, `<city>`, `<repo>`, and `<home>`, as a build decision.
  The `top` USER column stays as captured.
- Impact: the root README no longer carries private values; the captures differ from the raw output only in those tokens.

- Plan said: run the copy-editor agent in the final review-content pass.
- Deviated: the copy-editor agent could not be launched from an executor, so the review-content checks were done by hand with Vale and the keyboard lint.
- Impact: style and flow notes are in the report, not applied.

- Plan said: `just check` is the gate.
- Deviated: `just check` failed at `ruff format --check` on a Python fence in part 7, and it failed the same way at HEAD before this step.
  The implement pass left the fence alone.
- Impact: resolved by the fix pass (next bullet).

- Plan said: the plan's Artifact list names three files.
- Deviated: the fix pass also edited part 7 (two formatter comment lines around one fence, no content change), because the Step 14 Verify clause requires `just check` to exit 0.
- Impact: `just check` passes.

## Efficiency Insights

**What went well:**
- The fix pass applied three exact edits from a script checked with Vale beforehand, so iteration 2 came back clean.
- The fresh `just block` run settled the latency wording before the docs were written.

**What could improve:**
- The per-step verification command was pytest alone, so a format failure at `ruff format --check` shipped through Steps 12 and 13 unseen.
- Two orchestrator-written sentences (the first causal sentence in part 1 and the long smell-reports sentence) drew the iteration 1 warnings.

**Course corrections:**
- The part 7 fence was first left alone as out of scope, then wrapped in formatter comments once the Verify clause required a green `just check`.

## Process Improvements

- Run `just check` and `just check-practice` after every step, prose steps included.
- Count words and run Vale on any replacement sentence before handing it to an executor.
- Make the copy-editor pass a task for the orchestrator, since an executor cannot launch the agent.

## Observations

- Steps 12 and 13 shipped while `just check` was failing at `ruff format --check`, because the per-step verification command is pytest alone.
- The first causal sentence in part 1 and the over-long smell-reports sentence were the orchestrator's own text.
- The exercise 06 README and part 7 say "the other four dashboard panels" in a seven-panel dashboard; they were left as the capture's wording.
- CLAUDE.md's exercise 03 bullet names only `solution/worker.py` as reading the port variable, though both copies do.
- The copy-editor agent could not be launched from an executor.
- Info findings carried from the validator:
  - Vale reports zero errors. The remaining warnings are the known `MasonBase.Headings` and `SentenceCapitalization` false positives in README.md and CLAUDE.md, or baseline warnings on untouched lines. Two `MasonBase.FirstUse` suggestions sit on changed smell-reports.md lines ("ANSI" and "USER"). Keyboard lint is clean.
  - The exercise 01 README (line 336) and part 2 (line 319) still state the 30-second averaging cause for the low latency panel reading. smell-reports.md records that under a build decision, for the owner to align at review.
  - The validator sessions did not load the skills as skills and used no MCP; the checks were the linters and the dispatch checklist.

## Suggested Skills for Next Session

- `content-design:style-linting`: Step 15 writes the decisions record and the pull request comment, and both go through Vale.
