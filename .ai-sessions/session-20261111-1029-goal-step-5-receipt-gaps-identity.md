# Session Summary: Goal Step 5, The Identity View For The Receipt-Gap Helper

**Date**: 2026-11-11
**Duration**: one goal step (implement, three validator iterations, two fix passes, finalize); active time not tracked
**Conversation Turns**: seven subagent dispatches before this finalize dispatch
**Estimated Cost**: not tracked
**Model**: step executor: claude-sonnet-5-5; validator: claude-opus-5-5; orchestrator: claude-fable-5-2

## Goal Context

- **Condition**: not visible to the finalize dispatch
- **Mode**: step (Section 3 / Step 5 of the fleet-localization plan)
- **Outcome**: converged for this step (validator clean at iteration 3, the fix-pass cap)
- **Subagent dispatches**: implement, validator 1, fix 1, validator 2, fix 2, validator 3, finalize
- **Steps completed**: Step 5 checked off in `todo.md` (all 8 sub-steps)

## Key Actions

- Captured four real receipt histories from one live two-Worker bad flood on the single-binary dev server (exercise 06 practice copy, 10 receipts per second).
- Masked only `@<hostname>` to `@host` and saved them as `tests/fixtures/fleet-receipt-healthy.json`, `fleet-receipt-retried.json`, `fleet-receipt-failed.json`, and `fleet-later-timeout.json`.
- That one capture run printed `receipts submitted=514 failed=21`.
  This is one run, not a general result.
- Added `--by-identity` and `--summary` to `scripts/receipt_gaps.py`.
- New pieces: `IdentityFacts`, `ActivityFact`, `identity_facts` (a pure reducer over one history), `summarize_identities` (a pure fold over many), `format_identity_line`, and `span_ms`.
- `--summary` alone exits 2 through `parser.error`.
- Default output is unchanged byte for byte, pinned by a test.
- `tests/test_receipt_gaps.py` grew to 23 tests.
- Moved the `## Step 5` notes out of `.ai-sessions/implementation-notes.md` into this file.

## Prompt Inventory

The only user prompt in this arc is `/goal @goal.md`; the other rows are orchestrator dispatches.

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| `/goal @goal.md` | Started the autonomous run for the plan | Step 5 dispatched |
| Executor (Sonnet), `Mode: implement` | Captured and masked four fixtures, wrote the identity functions, the flags, and the tests | Tree dirty for validation, tests green |
| Validator (Opus), iteration 1 | Reviewed the diff against the Section 3 Tools block | Verdict `warn`: the docstring said one entry per WorkflowTaskTimedOut, the code skips a timeout with no WorkflowTaskStarted, and no test covered the skip |
| Executor (Sonnet), `Mode: fix` 1 | Reworded the docstring and added a derived schedule-to-start test, shown to have teeth by mutating the skip | Finding fixed, tests green |
| Validator (Opus), iteration 2 | Re-reviewed the diff | Verdict `warn`, two findings: the docstrings said `attempt N` appears only when a retry moved WT1 while the code prints it on every line with a WT1, and no test reached `largest WT1 none` or `on no Worker` |
| Executor (Sonnet), `Mode: fix` 2 | Reworded both docstrings and added two tests (21 became 23), each shown to fail under a temporary mutation | Findings fixed, tests green |
| Validator (Opus), iteration 3 | Re-reviewed the diff | Verdict `clean`, one info finding carried to the commit body |
| Executor (Sonnet), `Mode: finalize` | Gates, session summary, three lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: write the failing tests (RED) before the code (GREEN).
- Deviated: captured the fixtures, then wrote the identity functions and the flags, then the tests; the tests were never run red before the code existed.
- Impact: the default-output test was shown to have teeth by mutation instead (a default line gained a field, 5 tests failed, reverted).
  The new-behavior tests were not seen failing at first; the two fix passes later showed the added tests fail under mutation.

- Plan said: wire the flags through `main` and `receipt_ids`.
- Deviated: `receipt_ids` is unchanged; it only lists receipt Workflow IDs and needs no flag.
  Only `main` reads the flags.
- Impact: none.

- Plan said: capture a later-timeout Workflow in any type, derive it in a test if not captured.
- Deviated: the later-timeout history is a real receipt (its second Workflow Task timed out twice), so no derived history was needed for it.
  A separate test derives an ActivityTaskFailed history from the failed receipt, because no capture held one.
- Impact: none for the fixtures; the derived-history tests say "derived" in their names.

## Efficiency Insights

**What went well:**
- The fixtures are real histories, so the attribution tests run against what the server writes, not against a shape the executor guessed.
- Each added test was shown to fail under a temporary mutation, which separated a test that checks something from one that only runs the branch.
- The pure reducer and the pure fold keep the identity logic testable without a runner or a server.

**What could improve:**
- Two of the three validator passes failed on docstrings that said less or more than the code printed.
  The docstring was written before the formatter settled, and each correction found one more place it had drifted.
- The step used every allowed fix pass (iteration 3 is the cap), so a third docstring miss would have had no pass left.
- Skipping RED meant the new-behavior tests were first seen failing only during the fix passes.

**Course corrections:**
- Fix pass 1 reworded the module docstring and added the schedule-to-start test.
- Fix pass 2 reworded the `attempt N` and fallback-branch text and added two tests for `largest WT1 none` and `on no Worker`.

## Process Improvements

- Write a docstring that describes an output format last, from the formatter's branches, and read it against each branch once before the first validator pass.
- For each fallback branch the captured fixtures do not reach, plan a derived-history test in the same step, and run a mutation on it before handing the diff over.

## Observations

These are build decisions the owner will see at review; none is a ruling.

- The identity line layout (`wt1 on A -> B attempt N`, `wt timeout on A`, `<activity> TIMED OUT on A attempt N`) is the executor's choice.
- A Workflow Task that timed out with no Started event is not attributed to any identity.
- An Activity with no ActivityTaskStarted prints `on no Worker` and counts for no identity in the summary.
- The code does not use `started_event_id` on the timeout event as an attribution key; it uses the scheduled event id.
- `receipt_ids` is unchanged.
- A retried Activity's history keeps only its last attempt's ActivityTaskStarted.
  An attempt a frozen Worker swallowed before a retry ran elsewhere leaves no event that names the frozen identity.
  The module docstring says so.
- The temporal-docs MCP could not be loaded in the validator.
  The attribution claims (WorkflowTaskTimedOut carries no identity and points at its scheduled and started events; ActivityTaskStarted carries the scheduled event id, the identity, and the attempt) were checked against the installed temporalio 1.33.0 history protos, and they hold.
- CLAUDE.md, plan.md, spec.md, and the justfile are unchanged in this step; the CLAUDE.md update is deferred to Step 14.

## Suggested Skills for Next Session

- `python:python`: Step 6 is six housekeeping findings with no behavior change, all in Python code and tests.
