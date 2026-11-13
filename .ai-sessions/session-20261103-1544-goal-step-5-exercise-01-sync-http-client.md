# Session Summary: Goal Step 5, Exercise 01 Sync HTTP Client

**Date**: 2026-11-03
**Duration**: One autonomous step (implement, validate, two fix passes, finalize)
**Conversation Turns**: Few (dispatch-driven)
**Estimated Cost**: Moderate
**Model**: Sonnet 5.5 (finalize)

## Goal Context

Step 5 of the `/bpe:goal` run over the regenerated 14-step plan.
Creates exercises/01-sync-http-client/ with a solution/ and a practice/ copy.

## Key Actions

- Built the solution copy: flat imports, the bystander fleet, the freeze ordering, and a local slow upstream.
- The bug is `async def` geo activities calling a sync `httpx.Client` on the event loop.
  The fix is plain `def` activities run on a `ThreadPoolExecutor` passed as the worker's `activity_executor`.
- Built the practice copy: the same code before the fix, marker kept, with TODO comments and a probe test stub.
- Ticked the Step 5 checkboxes in `todo.md`.
- `just check` (92 root tests plus the solution gate) and `just check-practice` both exit 0.
- Live smoke from implement: practice reproduced the rollup timeout, solution completed cleanly.

## As-Built Design

- `get_ip` takes no arguments on the real providers.
  Only `get_location` takes `(ip, upstream_url)`, so the bad run freezes once, not twice.
- `slow_upstream.serve_slow_upstream(delay)` serves on 127.0.0.1 with an ephemeral port.
  The starter starts it.
- `mode`, `block_seconds`, and the `InvalidMode` path were removed from the copy.
- `HTTP_TIMEOUT_SECONDS` is 4.0 for the public providers.
  `UPSTREAM_TIMEOUT_SECONDS` is 60.0 and applies only to the slow upstream.
- The freeze gate uses a fixed 20 s lock-poll timeout, then a 3 s blind-pause fallback.
  Both warn loudly.
- `MAX_CONCURRENT_ACTIVITIES` feeds both the activity slots and the executor's `max_workers`.
- `# TODO PART C` sits at the signatures, and `# TODO PART D` sits at the executor and the test stub.
  Step 11 may want to realign these letters with the README's Part lettering.

## Fix Loop

- Iteration 1: narrowed the timeout scope and replaced a production assert.
- Iteration 2: an orchestrator-suggested executor-lifecycle change widened the Part D diff between practice and solution.
  It was reverted.
  The orchestrator queried the temporal-docs MCP and passed the result to subagents as a facts file.
- Iteration 3 validated clean.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Mode: implement, Step 5 | Created both exercise copies | Tests green, smoke passed |
| Mode: fix, iterations 1 and 2 | Timeout scope, assert, revert of widened diff | Validated clean at iteration 3 |
| Mode: finalize, Step 5 | Ran both gates, wrote this summary and a lesson, committed and pushed | See commit |

## Observations

- Cache directories under exercises/ are gitignored; `git status --untracked-files=all exercises/` lists only source and test files.
- CLAUDE.md still describes only the root package; the gate description waits for Step 13.
