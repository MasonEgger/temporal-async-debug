# Session Summary: Goal Step 4, The Exercise 06 Practice Copy

**Date**: 2026-11-11
**Duration**: one goal step (implement, validator iteration 1, one fix pass, validator iteration 2, finalize); active time not tracked
**Conversation Turns**: four subagent dispatches before this finalize dispatch, plus one orchestrator correction sent back to the implement executor
**Estimated Cost**: not tracked
**Model**: executor Opus (implement, fix, finalize), validator Fable (both iterations)

## Goal Context

- **Condition**: not visible to the finalize dispatch
- **Mode**: step (Section 2 / Step 4 of the fleet-localization plan)
- **Outcome**: converged for this step (validator clean at iteration 2)
- **Subagent dispatches**: implement (with one correction round), validator iteration 1, fix iteration 1, validator iteration 2, finalize
- **Steps completed**: Step 4 checked off in `todo.md` (all 8 sub-steps)

## Key Actions

- Added `exercises/06-finding-the-frozen-worker/practice/`, 12 files built from the solution copy.
- In `practice/activities.py`, `get_location` is back to `async def`, and its stdlib `sqlite3` cache lookup runs directly on the event loop.
- The antipattern marker sits on three comment lines directly above the lookup call, starting at `activities.py:166`.
- `practice/activities.py` carries `# TODO PART C:` above the marker and `# TODO PART D:` comments above `get_location` and above the `async with httpx.AsyncClient` block.
- `practice/worker.py` passes no `activity_executor` and no `max_concurrent_activities`, and carries a `# TODO PART D:` comment where the executor goes.
- The practice tests are `conftest.py`, `test_metrics_port.py`, and a `test_probe.py` stub that fails with `TODO PART D: write the probe test`.
- `flood.py`, `starter.py`, `db_lock.py`, `receipt.py`, `rollup.py`, `shared.py`, `workflow.py`, `tests/conftest.py`, and `tests/test_metrics_port.py` are byte-identical to the solution copy (checked with `cmp`).
- The justfile is unchanged: both gate loops glob `exercises/*/`, so `just check-practice` now prints a gate line for exercise 06 practice (ruff clean, mypy clean over 12 source files).
- `just check` exits 0 with 104 root tests and every solution copy green (exercise 06 solution: 51 tests); `just check-practice` exits 0.
- `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` still returns nothing.
- The implement pass ran one live check on one practice Worker; the outputs stay in the scratchpad.

## Prompt Inventory

The run was autonomous, so each row is a dispatch, not a user prompt.

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Executor (Opus), `Mode: implement` | Copied the solution, trimmed the tests, wrote the probe stub, restored the bug with the marker and TODO comments, removed the executor, ran the gates and one live check | Practice copy built, tree dirty for validation |
| Orchestrator correction to the implement executor | Withdrew the "never split the marker" instruction, which contradicted the house convention | The marker was wrapped over three comment lines and the file-level `# ruff: noqa: E501` was removed |
| Validator (Fable), iteration 1 | Reviewed the diff against the Section 2 Tools block (the temporal-docs MCP did not load) | Verdict `warn`, 1 finding (`spec.invariant`): the `async with httpx.AsyncClient` line and its `await client.get` call had no `# TODO PART D:` comment, unlike exercise 03's practice copy |
| Executor (Opus), `Mode: fix` | Added two comment lines in `practice/activities.py` (lines 147 and 174), nothing else | Finding fixed, tests green |
| Validator (Fable), iteration 2 | Re-reviewed the diff; the orchestrator also ran `ruff format --check` in the practice copy (12 files already formatted) | Verdict `clean`, two info findings carried to the commit body |
| Executor (Opus), `Mode: finalize` | Gates, session summary, two lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: the marker goes on the line above the lookup call, given as one line.
- Deviated: the marker is wrapped over three consecutive comment lines directly above the lookup call, words unchanged and in order, to match the other copies (exercises 01 to 05 and the root package) and the 120-column limit.
- Impact: no lint suppression in `practice/activities.py`; the marker grep still returns exactly one line for the practice copy (its first line, `activities.py:166`).

- Plan said: the practice stub carries "the imports the reader will need".
- Deviated: the stub imports only `pytest` at runtime and the `Path` and `respx` types under TYPE_CHECKING, and takes the `mocked_network` and `tmp_path` fixtures; the TODO PART D comment names `hold_cache_lock` from `db_lock.py`.
  Importing `get_location`, `hold_cache_lock`, and the rest unused would fail ruff F401 in `just check-practice`.
- Impact: matches exercise 01's stub, which imports only `pytest`.

- Plan said: no live check in this step.
- Deviated: ran one live check at the dispatcher's request: a fresh single-binary dev server (`temporal server start-dev --metrics-port 9465`), one practice Worker, and `uv run python starter.py --bad 1 --lead 2 --block-seconds 10 --tail 5`.
  The freeze was confirmed (no "freeze not confirmed" line), and the run printed `receipts submitted=193 failed=0`.
  All 100 receipts submitted in the two hold buckets were slower than 2 seconds (p50 10.91 s, then 6.38 s), and the rollup and the geo run completed.
  The Worker log had 58 lines matching `timed out` or `TMPRL`, `TMPRL1104` among them.
- Impact: the practice bug freezes the Worker as Step 7's captures need.
  This is one run, so it is not a general result.
  With one Worker no receipt failed; the spec puts the failures in the two-Worker fleet.

## Efficiency Insights

**What went well:**
- Starting from a byte copy of the solution kept the practice-to-solution diff to the fix lines, the marker, the TODO comments, and the tests.
- The gate loops already glob every exercise, so exercise 06 joined both gates with no justfile edit.
- One fix pass of two comment lines cleared the only warning.

**What could improve:**
- The orchestrator gave the implement executor a formatting rule ("never split the marker") without checking the existing markers, all of which wrap over several comment lines.
  The executor followed it, kept one 264-character line, and added a file-level `# ruff: noqa: E501`, which then had to be undone.
- The first pass missed two Part D edit points because it marked the function's kind change but not the HTTP client and request call that change with it.
  Exercise 03's practice copy, whose fix has the same shape, already marked them.

**Course corrections:**
- The marker was rewrapped over three comment lines and the `noqa` directive removed during implement.
- The fix pass added the `# TODO PART D:` line above the `async with httpx.AsyncClient` block and the second line of the comment above `get_location`.

## Process Improvements

- Before an orchestrator hands an executor a formatting rule, grep the existing files for the convention (here, `grep -rn -A2 "ANTIPATTERN (deliberate"`).
- When building a practice copy, diff its TODO comments against the sibling exercise whose fix has the same shape before the first validator pass.

## Observations

These are build decisions the owner will see at review; none is a ruling.

- The temporal-docs MCP could not be loaded by either validator pass, so the Temporal claims (an executor is required only for a non-async Activity; 100 slots per kind when no `max_*` argument is passed) were checked against the temporalio 1.33.0 source.
- `practice/worker.py`'s Part D comment says to size the executor "to the number of activity slots", but the practice copy names no slot number (by spec it passes no `max_concurrent_activities`).
  The exercise 06 README (Step 10, Part D) has to give the reader the SDK default of 100.
- The probe stub names `hold_cache_lock` in its TODO and imports nothing it does not use, so `just check-practice` stays green.
- CLAUDE.md, plan.md, spec.md, and the justfile are unchanged in this step; the CLAUDE.md update is deferred to Step 14.

## Suggested Skills for Next Session

- `python:python`: the next steps in the fleet-localization plan touch Python code and tests.
- `voice:teaching`: the exercise 06 README prose (Step 10) has to carry the Part D slot default noted above.
