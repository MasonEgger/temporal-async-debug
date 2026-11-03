# temporal-async-debug Implementation Plan (Failure-Mode Catalog)

This plan turns the catalog target in `spec.md` into an executable, test-driven build sequence on top of the committed two-workflow foundation.
Each step is a literal prompt for a code-generation LLM.
Feature steps follow RED/GREEN/REFACTOR; Task steps follow Scope/Tooling/Do/Verify/Document.
Steps build strictly on their predecessors with no orphaned code.

Read `spec.md` in full before starting; the `## Starting context` live-verified mechanics and the `## Architecture (target for the catalog)` and `## Behavior requirements (scenario catalog)` sections are the source of truth. Honor the `## Invariants`, `## Non-goals`, and `**Deferred:**` fences: no new dependencies, no role-labeled names, no lab mode / generator / game master, changes only under src/, tests/, justfile, README.md, CLAUDE.md.

## Current Status

- [ ] Section 1: Misbehavior Modes And The Starvation Probe
  - [ ] Step 1: Extend The Mode Set (cpu, slow_heartbeat, stuck_no_heartbeat)
  - [ ] Step 2: Extend The Starvation Probe To cpu And slow_heartbeat
- [ ] Section 2: Bystander Workflows
  - [ ] Step 3: Short-Work Bystander (SalesRollupWorkflow)
  - [ ] Step 4: Schedule-To-Start Sample (PriceQuoteWorkflow)
- [ ] Section 3: Workflow Timeout Selection Per Mode
  - [ ] Step 5: Per-Mode Activity Options In The Geo Workflow
- [ ] Section 4: Worker, Starter, And Recipes
  - [ ] Step 6: Register The Full Fleet On The Worker (task)
  - [ ] Step 7: Extend The Starter To The Full Scenario Set
  - [ ] Step 8: One Just Recipe Per Scenario (task)
- [ ] Section 5: Documentation
  - [ ] Step 9: Full README Catalog (task)
  - [ ] Step 10: Refresh CLAUDE.md Architecture (task)

## Architecture Recap (target)

Package `src/temporal_async_debug/` (src layout, hatchling, Python 3.14+). The foundation (GeoEnrichmentWorkflow, OrderReceiptWorkflow, block/slow modes, mistuned worker, fleet starter) is committed; this plan adds the delta.

- `shared.py`: add `VALID_MODES` (block, cpu, slow, slow_heartbeat, stuck_no_heartbeat) and the input/output dataclasses for the two new bystander workflow types.
- `activities.py`: `_apply_mode` gains cpu (GIL-pinning busy loop, marked), slow_heartbeat (awaits in steps and heartbeats, correct, unmarked), stuck_no_heartbeat (awaits long, never heartbeats, marked). block and slow carry over.
- `rollup.py` (new): `SalesRollupWorkflow` and `roll_up_sales`, a short (~2s) cooperative in-memory activity, correct and no network. The short-work bystander that a freeze catches in-flight.
- `quote.py` (new): `PriceQuoteWorkflow` and `compute_quote`, a near-instant in-memory activity whose options set a short `schedule_to_start_timeout` (marked). The sample that shows schedule_to_start firing under saturation.
- `receipt.py` (exists): `OrderReceiptWorkflow`, the instant bystander. Unchanged except worker registration.
- `workflow.py`: `GeoEnrichmentWorkflow` selects per-mode activity options via a pure `geo_activity_options(mode)` helper: generous `start_to_close` so slow / slow_heartbeat hold their slots the full duration, `heartbeat_timeout` for slow_heartbeat and stuck_no_heartbeat, `maximum_attempts=1` (marked) throughout.
- `worker.py`: register all four workflow types and every activity; keep `max_concurrent_activities=2` (marked) and the metrics endpoint.
- `starter.py`: extend `--mode` to the full set, add flags for the new bystanders, and sequence submissions so each scenario's timeouts fire deterministically live.
- `justfile`: one recipe per scenario.

Antipattern marker convention (fixed, greppable), on or immediately above each offending line:

```
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```

New marked lines this arc: the cpu busy loop (Step 1), the stuck_no_heartbeat missing-heartbeat branch (Step 1), and the PriceQuote `schedule_to_start_timeout` (Step 4). Carried over from the foundation: the `time.sleep` block call, the `maximum_attempts=1` retry policy, and `max_concurrent_activities=2`. `slow_heartbeat` is correct code and carries no marker.

Proposed new workflow names (neutral, adjustable at review): `SalesRollupWorkflow` (short-work bystander) and `PriceQuoteWorkflow` (schedule-to-start sample). Both are realistic and carry no role label.

## Section 1: Misbehavior Modes And The Starvation Probe

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 1: Extend The Mode Set (cpu, slow_heartbeat, stuck_no_heartbeat)

**NOTE**: The foundation's `activities.py` has `_apply_mode(mode, block_seconds)` handling `block` (time.sleep, marked) and `slow` (asyncio.sleep).
This step adds three modes.
`slow_heartbeat` must call `activity.heartbeat` but `_apply_mode` is also called from the Temporal-free starvation probe test, so guard every heartbeat with `activity.in_activity()` (a captured lesson).
cpu must NOT await and must NOT call time.sleep; it busy-loops on `time.monotonic()`.
Keep the mode branch a plain, obvious `if`/`elif` chain as the spec requires.

```text
1. RED: Extend the activity-behavior tests (via temporalio.testing.ActivityEnvironment, httpx mocked with the existing respx fixtures and deterministic_rotation autouse):
   - Modify tests/test_activities.py:
     - Test that mode "cpu" with block_seconds > 0 busy-loops: monkeypatch time.sleep and asyncio.sleep to record calls, run get_ip with a tiny block_seconds (for example 0.05), and assert neither time.sleep nor asyncio.sleep was called with a positive delay (cpu neither sleeps nor awaits its delay) while wall-clock elapsed is at least block_seconds.
     - Test that mode "slow_heartbeat" awaits asyncio.sleep and heartbeats more than once: set ActivityEnvironment.on_heartbeat to count calls, run get_ip with block_seconds = 0.09 (or a value that yields at least 2 steps given the step size chosen in GREEN), and assert the heartbeat count is >= 2 and asyncio.sleep was awaited.
     - Test that mode "stuck_no_heartbeat" awaits asyncio.sleep once and never heartbeats: on_heartbeat counter stays 0, asyncio.sleep recorded with block_seconds, time.sleep never called.
     - Test that VALID_MODES in shared.py equals the exact set {"block", "cpu", "slow", "slow_heartbeat", "stuck_no_heartbeat"}.
   - These test our mode branching and heartbeat behavior, not asyncio or Temporal internals.

2. Document component:
   - In src/temporal_async_debug/shared.py add a module-level VALID_MODES: tuple[str, ...] (or frozenset) constant with all five mode strings and a one-line Google-style comment naming what each mode demonstrates.
   - In src/temporal_async_debug/activities.py extend the _apply_mode docstring to describe cpu, slow_heartbeat, and stuck_no_heartbeat alongside block and slow.

3. GREEN: Write MINIMAL code to make tests pass:
   - Add VALID_MODES to shared.py.
   - Extend _apply_mode in activities.py with three new branches (keep block and slow unchanged):
     - cpu: compute deadline = time.monotonic() + block_seconds, then `while time.monotonic() < deadline: pass`. No await, no time.sleep. Marker on the loop line:
       # ANTIPATTERN (deliberate, for teaching): a CPU-bound loop pins the GIL and freezes the single worker event loop; it is uncancellable so the SDK cannot reclaim the slot. Correct: run CPU-bound work in a ProcessPoolExecutor off the event loop. Do not copy.
     - slow_heartbeat: loop the total block_seconds in fixed steps (step = 3.0 seconds, or the remaining time if smaller), awaiting asyncio.sleep(step) each iteration and, guarded by `if activity.in_activity():`, calling activity.heartbeat("slow_heartbeat progress") after each step. This is correct code; no marker.
     - stuck_no_heartbeat: await asyncio.sleep(block_seconds) once and never heartbeat. Marker immediately above the await:
       # ANTIPATTERN (deliberate, for teaching): this awaits long-running work but never heartbeats, so a workflow that sets heartbeat_timeout has the server cancel it mid-flight. Correct: heartbeat periodically during long work, as slow_heartbeat does. Do not copy.
   - Ensure _apply_mode stays async and the block/slow branches are untouched.

4. RED: Add an integration test:
   - In tests/test_activities.py, run get_ip end to end under ActivityEnvironment in mode "slow_heartbeat" with a small block_seconds and assert both the mocked IP result returns AND heartbeats fired, confirming the mode composes with the real activity body.

5. GREEN: Wire the branch so the integration test passes; adjust the step size only if needed to yield the asserted heartbeat count.

6. REFACTOR: Keep the five-way branch flat and readable for tutorial excerpting; no behavior change to block or slow.

7. Update documentation:
   - none (README is Step 9); confirm VALID_MODES and the extended docstrings are present.

8. Verify meaningful coverage of the three new mode branches, then run `just check`.
```

### Step 2: Extend The Starvation Probe To cpu And slow_heartbeat

**NOTE**: The foundation's tests/test_starvation_probe.py proves block starves a 50 ms probe and slow does not.
This step adds cpu (starves, like block) and slow_heartbeat (does not starve, like slow).
Reuse the same probe helper.
Pick thresholds with wide slack in one pass (a captured lesson): block/cpu against a floor well above 0.05 s, slow/slow_heartbeat well below.

```text
1. RED: Extend the probe test:
   - Modify tests/test_starvation_probe.py:
     - Add a cpu-mode case: run _apply_mode(mode="cpu", block_seconds=0.5) concurrently with the 50 ms probe and assert the probe misses ticks during the spin (a consecutive gap > 0.4 s).
     - Add a slow_heartbeat case: run _apply_mode(mode="slow_heartbeat", block_seconds=0.5) concurrently with the probe and assert the probe does NOT miss ticks (every consecutive gap < 0.2 s), proving cooperative awaits keep the loop scheduling even while heartbeating.
     - Parametrize the starving cases over ["block", "cpu"] and the non-starving cases over ["slow", "slow_heartbeat"] if it reads cleanly; otherwise keep them explicit.
   - These assert our starvation behavior, the exact teaching claim, not asyncio scheduling in the abstract.

2. Document component:
   - Update the module docstring in tests/test_starvation_probe.py to note the two families it now proves: uncancellable freezes (block, cpu) versus cooperative waits (slow, slow_heartbeat).

3. GREEN: Make the cases pass by calling the real _apply_mode from Step 1; add no new product code (slow_heartbeat's heartbeat is skipped outside an activity via the in_activity guard, so the probe test needs no worker).

4. RED: Add a comparative assertion:
   - Assert that cpu records strictly fewer probe ticks than slow_heartbeat over the same wall-clock window, making the freeze-vs-cooperative contrast a single comparison for the new pair.

5. GREEN: Adjust tick counts or thresholds minimally so both new assertions hold reliably; avoid tight bounds.

6. REFACTOR: Fold the four modes into the shared probe helper so block/cpu/slow/slow_heartbeat run through one code path; no product behavior change.

7. Update documentation:
   - none (README is Step 9).

8. Verify the cpu case fails if the cpu branch is switched to asyncio.sleep (sanity-check the assertion has teeth), revert, then run `just check`.
```

## Section 2: Bystander Workflows

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 3: Short-Work Bystander (SalesRollupWorkflow)

**NOTE**: This is the bystander a freeze catches in-flight.
Its one activity does a few seconds of cooperative in-memory work (no network) so that, when a freeze lands while it is running, it trips start_to_close, producing cross-type activity-timeout damage rather than only a stall.
It is correct code and carries no marker.
Name is neutral and adjustable; `roll_up_sales` sums an in-memory list with a short cooperative pause.
Keep it obviously correct so the tutorial can contrast it with the geo misbehaver.
Mirror the shape of the existing receipt.py.

```text
1. RED: Write the happy-path workflow test first (via temporalio.testing.WorkflowEnvironment.start_time_skipping):
   - Create tests/test_rollup.py:
     - Start a time-skipping WorkflowEnvironment, register SalesRollupWorkflow and roll_up_sales, run a Worker on shared.TASK_QUEUE, and execute SalesRollupWorkflow with SalesRollupInput(period="2026-09").
     - Assert the returned SalesRollupOutput.summary is a non-empty string that includes the period "2026-09".
     - Assert roll_up_sales performs no network: add an autouse forbid_network fixture (mirror tests/test_receipt.py) that monkeypatches httpx.AsyncClient.request to raise, so any accidental network call fails the test.
   - Add a unit test that roll_up_sales, run under ActivityEnvironment with a block/pause parameter of 0.0, returns the expected computed summary for a known input, so the aggregation logic is tested directly.
   - These test our rollup orchestration and computation, not Temporal or asyncio.

2. Document component:
   - Add a Google-style module docstring to src/temporal_async_debug/rollup.py naming this as a correct, unrelated bystander that shares the worker; docstrings on SalesRollupWorkflow and roll_up_sales.

3. GREEN: Write MINIMAL code to make tests pass:
   - Add SalesRollupInput(period: str) and SalesRollupOutput(summary: str) frozen dataclasses to src/temporal_async_debug/shared.py.
   - Create src/temporal_async_debug/rollup.py:
     - @activity.defn async def roll_up_sales(period: str, work_seconds: float = 2.0) -> str: compute a summary from an in-memory list of figures (a small module-level constant), awaiting asyncio.sleep(work_seconds) once to simulate the short cooperative work, then return a summary string mentioning the period and the computed total. No network, no time.sleep, no marker.
     - @workflow.defn class SalesRollupWorkflow with @workflow.run async def run(self, args: SalesRollupInput) -> SalesRollupOutput, executing roll_up_sales with start_to_close_timeout=timedelta(seconds=10) and schedule_to_close_timeout=timedelta(seconds=20) and the default retry policy, returning SalesRollupOutput(summary=...).
     - Use `with workflow.unsafe.imports_passed_through():` for the shared import, matching the foundation's workflow modules.

4. RED: Add a concurrent integration test:
   - In tests/test_rollup.py, run several SalesRollupWorkflow executions concurrently under one time-skipping environment and assert all complete with their distinct periods reflected, confirming the bystander path is independent and correct.

5. GREEN: Wire the workflow so the concurrent test passes; change nothing else.

6. REFACTOR: Keep rollup.py minimal and obviously correct; no behavior change.

7. Update documentation:
   - none (README is Step 9).

8. Verify meaningful coverage of the rollup computation and orchestration, then run `just check`.
```

### Step 4: Schedule-To-Start Sample (PriceQuoteWorkflow)

**NOTE**: This is the one place schedule_to_start_timeout appears, since setting it is rare.
The workflow models a task that is worthless if it does not start promptly (a late price quote is out of date), which is the legitimate routing/staleness use case, so the short schedule_to_start_timeout is realistic here yet still carries the marker because it is normally an antipattern.
The activity is near-instant in-memory; the timeout fires only because the worker is saturated when it is submitted.
Name is neutral and adjustable.

```text
1. RED: Write the happy-path workflow test first (via WorkflowEnvironment.start_time_skipping):
   - Create tests/test_quote.py:
     - Start a time-skipping WorkflowEnvironment, register PriceQuoteWorkflow and compute_quote, run a Worker on shared.TASK_QUEUE, and execute PriceQuoteWorkflow with PriceQuoteInput(sku="WIDGET-1", quantity=3).
     - Assert the returned PriceQuoteOutput.quote is a non-empty string including the sku "WIDGET-1".
     - Assert compute_quote performs no network (autouse forbid_network fixture as in Step 3).
   - Add a unit test asserting the workflow configures a schedule_to_start_timeout: expose the activity options via a small pure helper quote_activity_options() -> a mapping/params object in quote.py and assert it includes schedule_to_start_timeout == timedelta(seconds=5) and start_to_close_timeout set. This tests our timeout configuration, the teaching point, directly rather than trying to trip the timeout under time-skipping (which is flaky, a captured lesson).
   - These test our quote computation and its deliberate schedule_to_start configuration, not the Temporal runtime.

2. Document component:
   - Add a Google-style module docstring to src/temporal_async_debug/quote.py explaining the staleness rationale and that the short schedule_to_start_timeout is deliberately set to make saturation fail fast and visibly; docstrings on PriceQuoteWorkflow and compute_quote.

3. GREEN: Write MINIMAL code to make tests pass:
   - Add PriceQuoteInput(sku: str, quantity: int = 1) and PriceQuoteOutput(quote: str) frozen dataclasses to src/temporal_async_debug/shared.py.
   - Create src/temporal_async_debug/quote.py:
     - @activity.defn async def compute_quote(sku: str, quantity: int) -> str: compute a price from an in-memory price table (module constant) and return a quote string; near-instant, no sleep, no network.
     - A pure helper quote_activity_options() returning the activity options (start_to_close_timeout=timedelta(seconds=5), schedule_to_start_timeout=timedelta(seconds=5)) so the value is unit-testable and the workflow and the test share one source.
     - @workflow.defn class PriceQuoteWorkflow executing compute_quote with those options, returning PriceQuoteOutput(quote=...). Marker on the schedule_to_start_timeout in quote_activity_options:
       # ANTIPATTERN (deliberate, for teaching): a short schedule_to_start_timeout is normally an antipattern; it is set here only because a stale quote is worthless, and to make worker saturation fail fast and visibly. Correct: usually leave schedule_to_start unset and size the worker to demand. Do not copy.

4. RED: Add an integration assertion:
   - In tests/test_quote.py, run PriceQuoteWorkflow for several skus concurrently under time-skipping and assert each quote reflects its sku and quantity, confirming the sample path is correct when the worker is not saturated.

5. GREEN: Wire the workflow so the concurrent test passes; change nothing else.

6. REFACTOR: Keep quote.py minimal; no behavior change.

7. Update documentation:
   - none (README is Step 9).

8. Verify meaningful coverage of the quote computation and the options helper, then run `just check`.
```

## Section 3: Workflow Timeout Selection Per Mode

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

### Step 5: Per-Mode Activity Options In The Geo Workflow

**NOTE**: The foundation's workflow.py runs get_ip then get_location with fixed start_to_close (10s) plus schedule_to_close (15s) and maximum_attempts=1.
The catalog needs the geo activity options to depend on the mode: generous start_to_close so slow and slow_heartbeat hold their slots the full block duration (live-verified: an awaiting activity is cancelled at start_to_close), and a heartbeat_timeout for slow_heartbeat (which it satisfies) and stuck_no_heartbeat (which it does not, so it fails).
block and cpu keep a generous start_to_close and no heartbeat_timeout; they are detected from the frozen-loop stack, not from a timeout.
Extract the selection into a pure helper so it is unit-testable without a server.
Keep maximum_attempts=1 (marked) for every mode.

```text
1. RED: Write per-mode options tests first:
   - Create tests/test_geo_options.py (or extend tests/test_workflow.py):
     - Test a pure helper geo_activity_options(mode: str) -> an options object/params covering all five modes:
       - For "block" and "cpu": start_to_close_timeout is generous (== timedelta(seconds=120)), no heartbeat_timeout (None), maximum_attempts == 1.
       - For "slow" and "slow_heartbeat": start_to_close_timeout is generous (== timedelta(seconds=120)) so the awaiting activity holds its slot the full duration; for "slow_heartbeat" heartbeat_timeout == timedelta(seconds=10); for "slow" heartbeat_timeout is None.
       - For "stuck_no_heartbeat": heartbeat_timeout == timedelta(seconds=10) and start_to_close_timeout generous, so the missing heartbeat (not start_to_close) is what fails it.
       - Every mode: schedule_to_close_timeout set (== timedelta(seconds=150)) and retry_policy has maximum_attempts == 1.
     - Test that geo_activity_options rejects an unknown mode (raises ValueError) so a typo cannot silently produce default options.
   - This tests our timeout-selection logic, the catalog's teaching contract, not Temporal timeout enforcement.

2. Document component:
   - Add a Google-style docstring to geo_activity_options in src/temporal_async_debug/workflow.py mapping each mode to why its timeouts are set that way, referencing the live-verified mechanics in spec.md's Starting context.

3. GREEN: Write MINIMAL code to make tests pass:
   - In src/temporal_async_debug/workflow.py, add geo_activity_options(mode) returning the per-mode options (start_to_close_timeout, schedule_to_close_timeout, heartbeat_timeout or None, retry_policy=RetryPolicy(maximum_attempts=1)). Keep the maximum_attempts=1 antipattern marker on the retry policy line:
     # ANTIPATTERN (deliberate, for teaching): maximum_attempts=1 disables retries so the demo surfaces the first failure instead of masking it. Correct: allow retries with sensible backoff in production. Do not copy.
   - Rewrite GreetingWorkflow/GeoEnrichmentWorkflow's activity executions to build their kwargs from geo_activity_options(args.mode), passing heartbeat_timeout only when it is not None. Keep get_ip then get_location ordering and the returned output shape unchanged.

4. RED: Confirm the existing happy-path and error-path workflow tests still pass and, if needed, add one test that GeoEnrichmentWorkflow with mode "slow_heartbeat" runs to completion under start_time_skipping with stubbed activities (options applied without error).

5. GREEN: Adjust the execution wiring so all workflow tests pass; do not change get_ip/get_location signatures beyond passing block_seconds and mode through as before.

6. REFACTOR: Keep the activity-execution calls readable for excerpting; the per-mode branching lives only in geo_activity_options, not scattered in run().

7. Update documentation:
   - none (README is Step 9).

8. Verify meaningful coverage of every mode's options and the unknown-mode guard, then run `just check`.
```

## Section 4: Worker, Starter, And Recipes

### Step 6: Register The Full Fleet On The Worker (task)

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

**NOTE**: Wiring, so Task template.
The worker already registers GeoEnrichmentWorkflow and OrderReceiptWorkflow with max_concurrent_activities=2 (marked) and metrics on 127.0.0.1:9464.
This step adds the two new workflow types and their activities.
Keep the mistuning and the metrics endpoint; verified by import, not a unit test.

```text
1. Scope:
   - Artifact(s): src/temporal_async_debug/worker.py (edit)
   - Desired end state: `uv run python -c "import temporal_async_debug.worker"` succeeds; `uv run mypy .` passes; the Worker registers workflows=[GeoEnrichmentWorkflow, OrderReceiptWorkflow, SalesRollupWorkflow, PriceQuoteWorkflow] and activities=[get_ip, get_location, and the receipt, rollup, and quote activities], keeping max_concurrent_activities=2 (marker intact) and the Prometheus endpoint on 127.0.0.1:9464.

2. Tooling:
   - Skills: python:python, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources (only if a Worker keyword argument needs confirming)
   - External: uv, mypy, ruff

3. Do the work:
   - Import SalesRollupWorkflow and roll_up_sales from temporal_async_debug.rollup, and PriceQuoteWorkflow and compute_quote from temporal_async_debug.quote.
   - Add both workflows to the workflows= list and both activities to the activities= list on the existing Worker construction.
   - Leave max_concurrent_activities=2 and its antipattern marker unchanged; leave the Runtime/Prometheus config and the PID banner unchanged.

4. Verify:
   - Run `uv run python -c "import temporal_async_debug.worker"` and confirm exit 0, then run `just check` and confirm exit 0. (A live run against `temporal server start-dev` is a manual smoke test in the README, not part of this step.)

5. Document:
   - none here; the fleet is documented in the README in Step 9.
```

### Step 7: Extend The Starter To The Full Scenario Set

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

**NOTE**: The foundation's starter.py has a fleet CLI (--mode block|slow, --block-seconds, --bad, --geo, --receipts), a metrics parser (parse_activity_slots_available matching worker_type="ActivityWorker"), wait_for_free_activity_slots, and the os._exit(0) teardown workaround.
This step widens --mode to all five, adds flags for the two new bystanders, and sequences submissions so each scenario's timeouts fire deterministically live.
Argument parsing and input construction are our logic and are unit-testable without a server; the live submission ordering is thin and exercised manually.
Respect the live-verified mechanic (spec Starting context): to make a freeze trip a bystander's activity timeout, that bystander's activity must already be in-flight or scheduled BEFORE the freeze lands, because a frozen loop stops scheduling new activity tasks.

```text
1. RED: Extend argument-parsing and input-construction tests first:
   - Modify tests/test_starter.py:
     - Test that --mode accepts exactly the five VALID_MODES values (argparse choices sourced from shared.VALID_MODES) and rejects an invalid value with SystemExit.
     - Test that new flags --rollups (type int, default 0) and --quotes (type int, default 0) parse as ints and default to 0.
     - Test input-construction helpers: rollup_inputs_from_args(args) -> list[SalesRollupInput] produces --rollups items with distinct periods; quote_inputs_from_args(args) -> list[PriceQuoteInput] produces --quotes items with distinct skus.
     - Test that parsing a full flag set (--mode stuck_no_heartbeat --block-seconds 30 --bad 1 --geo 1 --rollups 2 --receipts 2 --quotes 1) yields exactly those typed values.
   - These test our CLI contract and input construction, not argparse itself.

2. Document component:
   - Update the src/temporal_async_debug/starter.py module docstring to describe the full --mode set, the new --rollups and --quotes flags, and, per scenario, what the fleet mix and ordering demonstrate.

3. GREEN: Write MINIMAL code to make tests pass:
   - Source the --mode choices from shared.VALID_MODES.
   - Add --rollups and --quotes flags (type int, default 0).
   - Add rollup_inputs_from_args and quote_inputs_from_args mirroring the existing bad_geo/healthy_geo/receipt helpers, with distinct labels (period, sku).
   - In main(), submit the fleet with ordering that makes the scenario deterministic:
     - For the freeze modes (block, cpu): submit the short-work bystanders (rollups) and any healthy geo first and wait until at least one activity slot is occupied (reuse the existing slot-polling helper), THEN submit the --bad geo run in the freeze mode, so the bystander is in-flight when the freeze lands and trips start_to_close. (Final, live-verified ordering: await the healthy geo before the bad run; submit receipts and quotes only after the server reports the bad run's second activity, get_location, STARTED plus a 1-second guard, so they stall through the final freeze and complete at the thaw instead of landing in the sub-second thaw between the two freezes, which ran 60 to 570 ms across the 8 final runs depending on get_ip's HTTP call and 138 ms in the run that exposed the race.)
     - For the saturation modes (slow, slow_heartbeat, stuck_no_heartbeat): submit the --bad geo runs to fill the slots, wait until parse_activity_slots_available reads 0, THEN submit the bystanders (receipts, rollups, quotes) so they starve and trip schedule_to_close (and, for quotes, schedule_to_start).
     - Keep the os._exit(0) teardown workaround.
   - Report each result (or failure) as the foundation's _report_results does; extend it to the new workflow types via its existing generic typing.

4. RED: Add an input-construction edge test:
   - In tests/test_starter.py, assert --rollups 3 yields three SalesRollupInput with three distinct periods and --quotes 2 yields two PriceQuoteInput with two distinct skus, so the fan-out is exercised without a server.

5. GREEN: Wire main() to use the helpers so submission and tests share one construction path.

6. REFACTOR: Keep parsing, input construction, and the per-scenario submission ordering as separate small functions so the tutorial can show the CLI surface cleanly; no behavior change.

7. Update documentation:
   - none (README is Step 9).

8. Verify meaningful coverage of parsing and input construction, then run `just check`.
```

### Step 8: One Just Recipe Per Scenario (task)

**Tools:** none

**NOTE**: Wiring, so Task template.
The justfile already has server, worker, trigger, and block/slow recipes for the fleet CLI.
This step adds a recipe per catalog scenario so a reader runs one command per lesson.
Recipes only compose the starter CLI; no new logic.

```text
1. Scope:
   - Artifact(s): justfile (edit)
   - Desired end state: `just --list` shows one recipe per scenario, each invoking `uv run python -m temporal_async_debug.starter` with the right flags; existing recipes still work.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: just

3. Do the work:
   - Keep the existing `default` recipe (`@just --list`) as the FIRST recipe in the justfile, so bare `just` prints the help; in just, the first recipe is the default, so new recipes must be added below it, never above it.
   - Add or update recipes (default seconds="30" where a duration applies), each a thin wrapper over the starter with a fleet mix that makes the scenario legible:
     - healthy: a fleet of geo + rollups + receipts + quotes, all healthy (block-seconds 0).
     - block seconds="30": --mode block --block-seconds {{seconds}} --bad 1 --geo 1 --rollups 1 --receipts 2 (freeze; rollup caught in-flight).
     - cpu seconds="30": --mode cpu --block-seconds {{seconds}} --bad 1 --geo 1 --rollups 1 --receipts 2 (freeze, GIL pinned).
     - slow seconds="30": --mode slow --block-seconds {{seconds}} --bad 2 --geo 1 --rollups 1 --receipts 2 --quotes 1 (saturation; quote trips schedule_to_start).
     - slow-heartbeat seconds="30": --mode slow_heartbeat --block-seconds {{seconds}} --bad 2 --receipts 2 --rollups 1 (correct long activity still saturates an undersized worker).
     - stuck seconds="30": --mode stuck_no_heartbeat --block-seconds {{seconds}} --bad 1 --geo 1 (heartbeat timeout fires).
   - Keep the recipe names matching the README lesson headings in Step 9.

4. Verify:
   - Run bare `just` and confirm it prints the recipe list (the default recipe survived as first). Run `just --list` and confirm every scenario recipe appears and parses (exit 0). Run `just check` and confirm exit 0. (Live behavior is verified manually while writing the README.)

5. Document:
   - none here; the recipes are documented in the README in Step 9.
```

## Section 5: Documentation

### Step 9: Full README Catalog (task)

**Tools:**
- Skills: python:python, temporal:temporal-developer, content-design:tutorial-writing, content-design:review-content
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: none

**NOTE**: The current README is stale (it describes the old Greeting/Victim design).
Rewrite it against the final catalog behavior.
Prose follows the writing hard rules: no em-dashes or en-dashes, one sentence per line in committed Markdown, straight quotes, sentence-case headings (this is a Temporal education doc).
Capture real tool output before writing the prose (a captured lesson): run the scenarios live against `temporal server start-dev` and the worker, and paste the genuine `asyncio ps` / `pstree`, `py-spy dump`, CPU, and metrics output rather than inventing it.
The live-verified diagnostic story (see spec.md Starting context, corrected October 2026) is two-tool: `asyncio ps` / `pstree` show the frozen-loop shape (the wedged task dead-ended at `_ActivityWorker._handle_start_activity_task`, the rest parked at awaits), and `py-spy dump` names the exact blocking line; `asyncio ps` does NOT show the blocking line, so do not claim it does.
The README and the GitHub repo description both state the repo contains deliberately broken code for educational purposes.
Invoke content-design:tutorial-writing before drafting and content-design:review-content after.

```text
1. Scope:
   - Artifact(s): README.md (rewrite)
   - Desired end state: the README is the in-repo tutorial home covering the full catalog: what the repo demonstrates, the three-terminal quickstart, one lesson per scenario, the mode-to-timeout-to-signature table, the two diagnostic families, platform gotchas, the realistic-timeouts framing, and a tutorial link placeholder.

2. Tooling:
   - Skills: content-design:tutorial-writing (invoke before drafting), content-design:review-content (invoke after drafting: Vale plus copy-editor), temporal:temporal-developer, python:python
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources (verify the exact metric names temporal_worker_task_slots_available and temporal_activity_schedule_to_start_latency, and how the poller LastAccessTime behaves in task-queue describe, before writing them into prose)
   - External: a running `temporal server start-dev` and worker for capturing real output; `py-spy` via `uvx py-spy dump --pid <worker-pid>` (no project dependency; needs ptrace_scope=0 or sudo); Vale via review-content

3. Do the work:
   - Capture real output first: start the server and worker, run each `just` scenario recipe, and save the genuine `asyncio ps` / `pstree` stacks, `py-spy dump` output (via `uvx py-spy dump --pid <worker-pid>`), CPU readings, metrics scrapes, and `temporal task-queue describe` for both healthy and broken states. Reuse any real captures already saved in the scratchpad from the investigation pass rather than recapturing identical output.
   - Rewrite README.md (sentence-per-line prose, no em-dashes, sentence-case headings) with:
     - A one-paragraph statement of what the repo demonstrates and a bold warning that it contains deliberately broken code for educational purposes only.
     - The headline: the cross-type blast radius (one workflow type takes down an unrelated one because they share a worker).
     - The two-tool diagnostic framing stated up front: `asyncio ps` / `pstree` show the frozen-loop shape with zero instrumentation (the wedged activity task dead-ended at `_ActivityWorker._handle_start_activity_task` with no await beneath it, while every other task is parked at a normal await), and `py-spy dump` names the exact blocking line in `activities.py`; explain that asyncio ps cannot show the line because a task stuck in synchronous code is not suspended at an await.
     - Quickstart: three terminals, `just server`, `just worker`, then a scenario recipe.
     - One lesson per scenario: healthy baseline, frozen loop blocking (block), frozen loop CPU (cpu), slot exhaustion (slow), correct long-running activity (slow_heartbeat), heartbeat timeout (stuck_no_heartbeat), and the schedule-to-start sample. Each lesson shows the expected healthy-versus-broken shapes for `asyncio ps` / `pstree` (the shape), `py-spy` (the line, for the freeze lessons), CPU, and the metrics, and names which timeout fires.
     - A summary table mapping each mode to the timeout it trips (start_to_close, schedule_to_close, schedule_to_start, heartbeat) and the tool signature that identifies it, with the frozen-loop versus saturated-worker split called out: freeze shows one task dead-ended at the SDK handler (block near-zero CPU, cpu at 100 percent, py-spy names the line, metrics reachable); saturation shows every task parked at a healthy await, slots at 0, task-queue backlog age climbing (poller LastAccessTime is not a freeze signal and at most a weak saturation hint).
     - Platform gotchas: inspector and target both Python 3.14+; `asyncio ps` and `py-spy` both read process memory, so on Linux Yama `ptrace_scope=1` blocks them (asyncio ps presents as "Failed to find the PyRuntime section"), fixed with sudo or `ptrace_scope=0`; macOS requires sudo; and 3.14 asyncio ps can fail transiently so re-run it.
     - The realistic-timeouts framing: start_to_close and schedule_to_close as the SLA, schedule_to_start as the rare routing case, the `task-queue describe` backlog age as the saturation tell (with `temporal_activity_schedule_to_start_latency` as a lagging confirmation that only moves once queued tasks start); and why workflow timeouts are not used (business logic depends on correctness, not time).
     - The antipattern marker convention and the grep for "ANTIPATTERN (deliberate, for teaching)".
     - A tutorial link placeholder pointing at masonegger.com (marked TODO).

4. Verify:
   - Invoke content-design:review-content on README.md and address every finding (Vale mechanical checks plus the copy-editor prose pass).
   - Human-check: read README.md top to bottom and confirm no em-dashes or en-dashes, one sentence per line in prose, sentence-case headings, that every command and metric name matches the code, that the captured output is real (not invented), and that the deliberately-broken-code warning is present.

5. Document:
   - This step is the documentation.
```

### Step 10: Refresh CLAUDE.md Architecture (task)

**Tools:** none

**NOTE**: The current CLAUDE.md architecture section still describes the old Greeting/Victim design, heartbeats, and the old flags.
Refresh it to the catalog's module and mode layout.
Same writing rules apply.
This is a straight documentation update with no code change.

```text
1. Scope:
   - Artifact(s): CLAUDE.md (edit the Architecture section and the Commands section)
   - Desired end state: CLAUDE.md's Architecture section names the real modules (shared.py, activities.py with the five modes, workflow.py with GeoEnrichmentWorkflow and geo_activity_options, receipt.py, rollup.py, quote.py, worker.py, starter.py) and the real demo recipes; no reference to victim.py, GreetingWorkflow, or the old flags remains.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: none

3. Do the work:
   - Update the Architecture section to the module list above, describing the shared single event loop, the five misbehavior modes, the cross-type blast radius across the four workflow types, and the frozen-loop-versus-saturation diagnostic split (asyncio ps / pstree for the frozen-loop shape, py-spy dump for the exact blocking line, CPU to separate block from cpu, task-queue backlog age for saturation).
   - Update the Commands section's demo recipes to match the justfile from Step 8 (healthy, block, cpu, slow, slow-heartbeat, stuck).
   - Keep the antipattern marker convention section; confirm the grep string matches the code.
   - Apply the writing rules: no em-dashes, one sentence per line in committed Markdown prose.

4. Verify:
   - Grep CLAUDE.md for "victim", "Greeting", and "VictimWorkflow" and confirm no stale references remain. Confirm the module list matches `ls src/temporal_async_debug/`. Run `just check` and confirm exit 0 (no code changed, so this just re-confirms the tree is green).

5. Document:
   - This step is the documentation.
```

## Implementation Guidelines

- All Python code follows the python:python skill without exception: full type hints, Google-style docstrings on public interfaces, no single-letter names, canonical ruff/mypy/pytest config blocks. Use PEP 695 generics and X | None as the foundation already does.
- Demo code stays small and readable; it is excerpted line-by-line in the tutorial. Comment density serves a reader learning the failure mode.
- Every deliberate bug, mistuning, or antipattern carries the fixed marker `# ANTIPATTERN (deliberate, for teaching): <why>. Correct: <right approach>. Do not copy.` on or immediately above the offending line. The validator flags any mistuning that lacks one. slow_heartbeat is correct and carries no marker.
- No new dependencies (Invariants: temporalio only, deps not to be added without a spec change). All new modes use stdlib (asyncio, time) and the existing httpx/temporalio.
- No role-labeled names (no victim, villain, culprit). New workflow types are neutral and realistic.
- Do not implement anything in Non-goals or the Deferred list (no fleet generator, no seeded culprit, no game master, no web UI, no CI changes, no Docker).
- Tests must not require a running Temporal server except through the SDK's own facilities (ActivityEnvironment, WorkflowEnvironment.start_time_skipping). Network is always mocked. Guard activity.heartbeat with activity.in_activity() in code reused outside an activity.
- Prefer start_local over start_time_skipping when a test involves schedule_to_start timing (a captured lesson); here, schedule_to_start is asserted via the options helper, not by tripping it under time-skipping.
- The full local gate is `just check` (ruff check, ruff format --check, mypy strict, pytest). Autonomous-run verification is pytest alone.
- Live failure signatures (cross-type blast radius, slot timing, CPU pinning, heartbeat and schedule-to-start timeouts) are captured live while writing the README, not asserted in CI.
- Writing rules apply to all prose (README, CLAUDE.md, docstrings, commit messages): no em-dashes or en-dashes, straight quotes, one sentence per line in committed Markdown.
- Never commit to main; work on a feature branch. Only Mason merges to main.

## Success Metrics

- `just check` passes: ruff clean, ruff format check clean, mypy strict clean, all tests green.
- Activity tests prove each of the five modes does what it claims: block calls time.sleep, cpu busy-loops without awaiting or sleeping, slow awaits asyncio.sleep, slow_heartbeat awaits and heartbeats more than once, stuck_no_heartbeat awaits and never heartbeats; the healthy path applies no delay; provider failover still works.
- The starvation probe deterministically shows block and cpu starve the probe while slow and slow_heartbeat do not, and the cpu case fails if its branch is switched to a cooperative await.
- The two new bystander workflows (SalesRollupWorkflow, PriceQuoteWorkflow) pass happy-path and concurrent tests under start_time_skipping with no network, and PriceQuoteWorkflow's options helper sets the marked schedule_to_start_timeout.
- geo_activity_options returns generous start_to_close for every mode, a heartbeat_timeout for slow_heartbeat and stuck_no_heartbeat, maximum_attempts=1 throughout, and raises on an unknown mode.
- worker.py registers all four workflow types and every activity, keeps max_concurrent_activities=2 (marked) and the metrics endpoint, and imports cleanly.
- The starter exposes all five modes and the --rollups/--quotes flags, constructs distinct inputs per bystander, and sequences submissions so freeze scenarios catch bystanders in-flight and saturation scenarios starve them.
- Every deliberately wrong line (time.sleep, the cpu loop, stuck_no_heartbeat missing heartbeat, the quote schedule_to_start_timeout, maximum_attempts=1, max_concurrent_activities=2) carries the exact antipattern marker and is greppable.
- The README documents every scenario with real captured healthy-versus-broken output, the mode-to-timeout-to-signature table, the platform gotchas, and the deliberately-broken-code warning; CLAUDE.md's architecture section matches the shipped modules with no stale Greeting/Victim references.
