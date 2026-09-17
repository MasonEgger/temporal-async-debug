# Session Summary: Step 5 Misbehaving Greeting Workflow

**Date**: 2026-09-17
**Duration**: ~15 minutes across implement, two fix passes, and finalize
**Conversation Turns**: 5 subagent dispatches (implement, validator, fix, validator, fix, validator, finalize span)
**Estimated Cost**: low-to-moderate (short dispatches plus two fix round trips, no research)
**Model**: claude-opus-4-8

## Goal Context

- **Condition**: build the async-debug demo by working plan.md top to bottom
- **Mode**: step (Step 5 of 10)
- **Outcome**: converged for this step (validator verdict clean at iter 3)
- **Turn count**: 7 orchestrator turns
- **Subagent dispatches**: 4 `bpe:step-executor` invocations (implement, two fix, finalize) plus 3 `bpe:validator` reviews
- **Steps completed**: 5 of 10

## Key Actions

- Created `src/temporal_async_debug/workflow.py` with `GreetingWorkflow`, which runs `get_ip` then `get_location` in sequence and assembles the greeting from the results.
- Set each activity call to a 60-second `start_to_close_timeout` and a 10-second `heartbeat_timeout`, so an activity that blocks the worker's event loop stops heartbeating and times out well inside its budget.
- Marked `RetryPolicy(maximum_attempts=1)` as the deliberate antipattern with a fixed, greppable `# ANTIPATTERN (deliberate, for teaching): ...` comment, so the first failure surfaces to the caller instead of being retried and hidden.
- Pulled the two timeouts into documented module constants (`ACTIVITY_START_TO_CLOSE_TIMEOUT`, `ACTIVITY_HEARTBEAT_TIMEOUT`) so the margins read in one place.
- Created `tests/test_workflow.py`: a happy-path test that proves the two-activity sequence and greeting shape (the stubbed `get_location` asserts it received the ip `get_ip` produced, pinning the ordering), and an error-path test that proves `maximum_attempts=1` surfaces the first failure without retrying.
- Ran both tests under `WorkflowEnvironment.start_time_skipping` with stub activities, so no test touches the network.
- Ran `just check` to exit 0: ruff check, ruff format --check (22 files), mypy strict (11 source files), pytest (23 passed).
- Cleared the validator's two findings across two fix passes (see Deviations from Plan), reaching verdict clean at iter 3.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| `/bpe:goal` dispatch, Mode: implement, Step 5 | Executed plan.md Step 5 RED/GREEN/REFACTOR sub-steps, checked off all 8 todo boxes | `just check` exit 0, tree dirty, ready for validation |
| `/bpe:goal` dispatch, `bpe:validator`, iter 1 | Reviewed the diff against `python:python`, `temporal:temporal-developer`, ruff, mypy | Verdict block: error-path test asserted only the exception type, never the attempt count |
| `/bpe:goal` dispatch, Mode: fix, iter 1 | Strengthened the error-path test to assert `attempts == [1]` and walk the cause chain to the stub message | Tests green, tree dirty, ready for re-validation |
| `/bpe:goal` dispatch, `bpe:validator`, iter 2 | Re-reviewed the diff | Verdict warn: attempt-count state was a module-level mutable list cleared inline |
| `/bpe:goal` dispatch, Mode: fix, iter 2 | Moved the counter to a closure-local `attempts` list over a nested `get_ip_failing` stub, dropping the module-level state | Tests green, tree dirty, ready for re-validation |
| `/bpe:goal` dispatch, `bpe:validator`, iter 3 | Re-reviewed the diff | Verdict clean, zero findings |
| `/bpe:goal` dispatch, Mode: finalize, Step 5 | Re-ran `just check`, wrote this summary, generated the commit message, committed and pushed | Single signed commit on `scaffold` |

## Deviations from Plan

- Plan said: put the `timedelta` import inside the `with workflow.unsafe.imports_passed_through():` block alongside the shared types.
- Deviated: placed `from datetime import timedelta` at module top level; only `shared` types and the two activity functions go through the pass-through block.
- Impact: none. `timedelta` is a standard-library type the Temporal sandbox already passes through safely; keeping it at top level reads conventionally and `just check` stays clean.

- Plan said: an error-path test asserting the workflow raises `WorkflowFailureError` was enough to prove the no-retry behavior.
- Deviated (validator iter 1 fix): the type-only assertion never observed the attempt count and would pass unchanged with `maximum_attempts=2` or `3`. The test now records `activity.info().attempt` per invocation and asserts `attempts == [1]`, plus walks the cause chain `WorkflowFailureError -> ActivityError -> ApplicationError` to the stub message, so the failure is the stubbed error and not a timeout.
- Impact: the test now has teeth. Temporarily bumping `maximum_attempts` to 2 makes the list `[1, 2]` and the test fails; production retry policy stays at the deliberate `maximum_attempts=1`.

- Plan said: (follow-on from the fix above) hold the attempt count in a module-level list cleared inline at the top of the test.
- Deviated (validator iter 2 fix): the python skill's tdd-workflow rule forbids module-level mutable state reset by an inline `.clear()`. Replaced it with a closure-local `attempts: list[int] = []` and a nested `@activity.defn(name="get_ip")` stub closing over it, registered on the Worker. No shared module state, no inline clear, no fixture needed.
- Impact: the test keeps its teeth (still asserts exactly one attempt and still walks the cause chain) while satisfying the skill's state-isolation rule. `workflow.py` was untouched across both fix passes.

## Efficiency Insights

**What went well:**

- Both fixes stayed inside `tests/test_workflow.py`; `workflow.py` was never touched during the fix loop, so the deliberate antipattern under test never drifted.
- Verifying the strengthened test's teeth once (bump `maximum_attempts` to 2, watch it fail, restore) confirmed the assertion actually constrains the retry policy rather than just passing.

**What could improve:**

- The first-pass error-path test asserted only the exception type, which cost a full validator round trip. Writing the attempt-count assertion up front would have skipped the block finding.

**Course corrections:**

- Iter 1 added attempt-count teeth; iter 2 moved that new state from module level into a closure so it isolated per test without a fixture.

## Process Improvements

- When a test's name claims a behavior (here, "without retrying"), assert the observable that distinguishes it (the attempt count), not just the exception type the behavior happens to raise.
- Keep new test-only state (counters, recorders) closure-local from the start; a nested `@activity.defn` stub over a local list needs no module-level variable and no reset fixture.

## Observations

- `WorkflowEnvironment.start_time_skipping` runs both the happy path and the no-retry failure without a real server, and stub activities keep every test off the network.
- Registering a second `@activity.defn(name="get_ip")` stub (the failing one) on a per-test Worker cleanly overrides the module-level stub for that test; the `name=` binding is what the workflow resolves against, not the Python function identity.

## Suggested Skills for Next Session

- `python:python`: Step 6 continues in strict-typed Python with pytest conventions.
- `temporal:temporal-developer`: the next steps wire the worker and runner around this workflow, where task-queue and activity-registration model matters.
