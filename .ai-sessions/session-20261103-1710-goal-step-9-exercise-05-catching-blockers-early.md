# Session Summary: Goal Step 9, Exercise 05 Catching Blockers Early

**Date**: 2026-11-03
**Duration**: One autonomous step (implement, validate, three fix passes, finalize)
**Conversation Turns**: Few (dispatch-driven)
**Estimated Cost**: High (several blocker redesigns with live measurement)
**Model**: Sonnet 5.5 (finalize)

## Goal Context

Step 9 of the `/bpe:goal` run over the regenerated 14-step plan.
Creates exercises/05-catching-blockers-early/ with a solution/ and a practice/ copy.
Validated clean at iteration 3.

## Key Actions

- Built the solution copy: `async def get_location` runs the archive step through `await asyncio.to_thread(_archive_audit_trail, ...)`.
- Built the practice copy: the same call made inline on the loop, marker kept, `# TODO PART C` at the call and `# TODO PART D` in the probe test stub.
- Added `worker.ACTIVITIES` and a time-skipping test that the registered `async def` activities equal the probed set.
- Ticked the Step 9 checkboxes in `todo.md`.
- Final gates: `just check` exit 0 (10 passed in the solution directory), `just check-practice` exit 0 for all practice copies.
- `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` is empty across all five exercises.
- `git status --porcelain --untracked-files=all exercises/` lists only .py source and test files, no caches.

## As-Built Design

- Blocker: one `zlib.compress(trail, 9)` over a stand-in audit trail of `os.urandom(PAYLOAD_RECORDS * RECORD_BYTES)` bytes.
  `PAYLOAD_RECORDS` is 22,000 and `RECORD_BYTES` is 480, about 10.5 MB.
  The bytes are prebuilt at import and cached, so the per-call cost is the compress alone, about 350 ms inline.
- Fix: the plan's one-line `await asyncio.to_thread(_archive_audit_trail, ...)`.
  A comment says `to_thread` is safe only because the work is short and bounded and there is no `heartbeat_timeout`.
- Every geo run stalls.
  There is no `--bad` flag in this exercise.
- Starter gate: a 20 ms `describe()` poll plus a 25 ms guard before submitting the receipts.
- `worker.ACTIVITIES` is a tuple.
  A time-skipping test asserts the registered `async def` activities equal the probed set.
- Practice `# TODO PART D` names `worker.ACTIVITIES`.

## Deviations from Plan

This decision path revises a confirm-at-review decision in spec.md.
Line 253 of spec.md still says "a pure-Python JSON round trip of a generated payload".
That decision text needs the user's confirm-at-review.

- Plan said: a synchronous JSON round trip of a generated payload (200 to 500 ms) as the blocker, fixed by `to_thread` or a `def` activity on the executor, with the diff limited to the serialization line.
- Deviated: the path took four attempts.
  1. The implement dispatch's pure-Python JSON blocker with any thread-based fix kept the probe green but left the receipts' first workflow task at 357 to 617 ms, because of GIL contention with the workflow-task thread.
     A `ProcessPoolExecutor` fixed it (15 to 38 ms) but the validator rejected it as a Deferred-item leak, against Temporal guidance, and against exercise 03's lesson.
  2. A `json.dumps` plus `zlib` blocker with `to_thread` did not recover: solution 333 to 377 ms against practice 303 to 338 ms.
  3. The all-C blocker, `zlib.compress` over prebuilt bytes, with `to_thread` did recover.
- Impact (final design): receipts' first WorkflowTaskStarted-to-WorkflowTaskCompleted gap, 3 runs x 3 receipts, no debug: practice 267 to 345 ms, solution 18 to 49 ms, healthy 16 to 30 ms.
  `PYTHONASYNCIODEBUG=1` gave 3 slow-callback warnings in practice and 0 in solution.
  The isolation probe (5 ms ticker beside `asyncio.to_thread`) showed a max gap of 12 to 17 ms.
  With the call inline, the probe test fails for `get_location`, so the guard has teeth.

- Plan said: the delay is visible as the receipt activity's started-to-completed gap.
- Deviated: the receipts' first workflow task is the one dispatched into the stall, so the visible symptom is the first WorkflowTaskStarted-to-WorkflowTaskCompleted gap (350 to 416 ms practice against 16 to 30 ms healthy).
  Activity started-to-completed gaps are 6 to 68 ms in both copies.
  Also, the asyncio debug-mode warning names the SDK handler task `_ActivityWorker._handle_start_activity_task`, not `get_location`.
- Impact: prose corrections for Steps 10, 11, and 13.
  They should quote the workflow-task gap and the SDK handler name.

## Process Notes

- The implement dispatch left about 13 orphaned multiprocessing forkserver and resource_tracker processes from its process-pool trials.
  A bulk kill was denied by the permission classifier, and no bypass was attempted.
- `pgrep -af 'multiprocessing|forkserver|resource_tracker'` at finalize returned nothing, so none remain.
- The `describe_namespace retried 5 times` WARN in the test log is the SDK's teardown noise; both gates exit 0.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Mode: implement, Step 9 | Built both copies, tried thread, process-pool, json+zlib blockers | Tests green, recovery not yet shown |
| Mode: fix, iterations 1 to 3 | Rejected process pool, moved to GIL-releasing zlib blocker, added worker.ACTIVITIES test | Validated clean at iteration 3 |
| Mode: finalize, Step 9 | Ran both gates, wrote this summary, committed and pushed | See commit |

## Suggested Skills for Next Session

- python:python
- temporal:temporal-developer
