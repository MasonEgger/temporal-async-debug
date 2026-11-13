# Session Summary: Goal Step 3, The Flood Starter

**Date**: 2026-11-11
**Duration**: one goal step (implement, three validator dispatches for two iterations, one fix pass, finalize); active time not tracked
**Conversation Turns**: five subagent dispatches before this finalize dispatch
**Estimated Cost**: not tracked
**Model**: executor claude-opus (implement, fix, finalize), validator Fable (both iterations)

## Goal Context

- **Condition**: not visible to the finalize dispatch
- **Mode**: step (Section 2 / Step 3 of the fleet-localization plan)
- **Outcome**: converged for this step (validator clean at iteration 2)
- **Subagent dispatches**: implement, validator iteration 1 (died on a usage limit), validator iteration 1 re-dispatched unchanged, fix iteration 1, validator iteration 2, finalize
- **Steps completed**: Step 3 checked off in `todo.md` (all 8 sub-steps)

## Key Actions

- Added `exercises/06-finding-the-frozen-worker/solution/flood.py` (218 lines), the flood plan and the summary as pure functions with no I/O and no Temporal import.
- `flood.py` holds `due_time`, `flood_due_times`, `planned_duration`, `summarize`, `format_bucket`, and `format_summary`, over the `ReceiptRecord`, `Bucket`, and `FloodSummary` dataclasses.
- Added `exercises/06-finding-the-frozen-worker/solution/starter.py` (392 lines): the argparse parser, the freeze gate `wait_for_activity_started`, the receipt producer `_produce`, and `run_flood`.
- The bad flood submits the rollup, then the bad geo run, then arms the cache lock, then gates on `get_location` reporting STARTED before the tail and the summary.
- The healthy flood (`--bad 0`) takes no lock and submits the same planned receipt stream.
- Added `tests/test_flood.py` (11 tests) and `tests/test_starter.py` (16 tests, counting parametrized cases); the flow tests run against a recording fake client and a fake lock.
- The fix pass added `test_a_started_get_ip_never_opens_the_gate` (two cases, with the activity names written as literals) and two late-wake tests driven by a virtual clock that the fake sleep advances.
- The exercise 06 solution suite went from 24 to 51 tests; `just check` exits 0 with 104 root tests and every solution copy green, and `just check-practice` exits 0.
- The implement pass ran a live healthy smoke flood and one short bad flood against a dev server and the Worker; the outputs stay in the scratchpad.

## Prompt Inventory

The run was autonomous, so each row is a dispatch, not a user prompt.

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Executor (Opus), `Mode: implement` | Tests first, then `flood.py`, the parser and gate, the producer and flow, the refactor, and the live smoke check | All sub-steps done, tree dirty for validation |
| Validator (Fable), iteration 1 | Started the review | Died on a usage limit with no verdict |
| Validator (Fable), iteration 1, re-dispatched unchanged | Reviewed the diff against the Section 2 Tools block (the temporal-docs MCP did not load) | Verdict `warn`, 2 findings: the late-wake rule ran in no test, and no test could fail on the gate's activity-name check |
| Executor (Opus), `Mode: fix` | Added a virtual clock and two late-wake tests; added the `get_ip` gate test with literal activity names | Both findings fixed, tests green |
| Validator (Fable), iteration 2 | Re-reviewed the diff | Verdict `clean`, info findings carried to the commit body |
| Executor (Opus), `Mode: finalize` | Gates, session summary, two lessons, commit, push | This commit |

## Deviations from Plan

- Plan said: check Temporal claims against the temporal-docs MCP.
- Deviated: the MCP tool was not available in the dispatch, so the SDK facts the starter relies on (`WorkflowFailureError.cause`, `FailureError.__str__` returning the message, the `__cause__` chain) were checked against the installed temporalio 1.33.0 source and a one-line interpreter check.
- Impact: none on behavior; the validator could not load the MCP either.

- Plan said: write the flow test in sub-step 4, after the parser and gate were green.
- Deviated: the flow tests were written in sub-step 1 with the other tests, and all of them were seen failing together (both modules missing) before any code was written.
- Impact: the test file is the same; the RED for the flow was observed once, not twice.

- Plan said: the healthy flood is "the same stream, same length, no lock held"; it does not say whether rollups run.
- Deviated: the healthy flood also submits `--rollups` rollups after the lead, so the two floods differ only in the bad run and the lock.
- Impact: the healthy summary prints one rollup outcome line.

- Plan said: nothing on a producer that falls behind.
- Deviated: a wake more than one spacing late shifts every later due time by that delay, so receipts never fire as a catch-up batch, and the starter prints one note with the total slip; a wake within one spacing is treated as timer jitter.
- Impact: documented in `_produce`; the recorded submit offsets are the real ones, so the timeline stays honest.

- Plan said: the slow count is "slower than 2 seconds"; the median and slowest are per bucket.
- Deviated: failed receipts count in the slow count, the median, and the slowest, using the time from submit to failure.
- Impact: a failed receipt reads as slow in its bucket, which matches it having taken at least 10 seconds.

- Plan said: run only the healthy smoke flood.
- Deviated: one short bad flood (`--bad 1 --lead 2 --block-seconds 3 --tail 2`) also ran on the same server and Worker to exercise the lock and the gate live; it confirmed the freeze, failed 0 of 83 receipts, and the rollup and the geo run completed.
- Impact: none on the repository; the outputs stay in the scratchpad.

- Plan said: stop the Worker and the server by their recorded PIDs.
- Deviated: the backgrounded `uv run` Worker ignored SIGINT, so it got SIGTERM by its recorded uv PID and by the python PID its banner printed; the server stopped on SIGINT.
- Impact: none; all four ports were free afterwards.

## Efficiency Insights

**What went well:**
- `flood.py` stayed pure, so the bucketing, the totals, and the line format are tested with plain records and no fake client.
- One fix pass cleared both warnings, and the second validator iteration came back clean.

**What could improve:**
- No first-pass test could fail on the gate's activity-name check: a fake whose name agrees with the code under test agrees with a wrong `FREEZE_GATE_ACTIVITY` (`get_ip`) too.
- The late-wake branch in `_produce` only runs when a sleep wakes late, and the first fake sleep never did, so the branch ran in no test.
- One validator dispatch died on a usage limit and had to be re-dispatched unchanged.

**Course corrections:**
- The gate tests now name `get_ip` and `get_location` as literals, and a started `get_ip` must never open the gate.
- A `_VirtualClock` patched over `monotonic` and `asyncio.sleep` advances on each sleep and adds a chosen delay at one wake, so both sides of the one-spacing rule run.

## Process Improvements

- When a test fake reports a value, write the expected value as a literal in the test, never import it from the module under test.
- For any branch that depends on wall-clock timing, add the virtual clock in the RED pass, not after review.

## Observations

These are build decisions the owner will see at review; none is a ruling.

- The healthy flood also submits `--rollups` rollups, so the two floods differ only in the bad run and the lock.
- The producer's late-wake rule: a wake more than one spacing late shifts every later due time, the starter prints one note with the total slip, and no catch-up batch fires.
- Failed receipts count in `slow>2s`, `p50`, and `max` with their submit-to-failure time.
  The earlier spike script used the same rule; Step 7's captures should confirm what a real bad flood prints.
- The bucket line loses the space after "submitted" at three-digit offsets, which only a `--block-seconds` near 100 or more reaches.
- `--rate inf` or `--rate nan` passes the parser.
- The temporal-docs MCP could not be loaded in any dispatch of this step, so the SDK claims were checked against the installed temporalio 1.33.0 source.
- The solution copy carries no antipattern marker, per the solution-copy carve-out.
- CLAUDE.md, plan.md, and spec.md are unchanged in this step.

## Suggested Skills for Next Session

- `python:python`: Step 4 builds the exercise 06 practice copy and wires it into the gates.
- `voice:teaching`: the exercise 06 README prose follows once the practice copy exists.
