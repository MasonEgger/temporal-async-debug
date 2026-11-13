# temporal-async-debug Implementation Plan (Fleet Localization)

This plan turns the `fleet-localization` arc in `spec.md` into an executable, test-driven build sequence.
Each step is a literal prompt for a code-generation LLM.
Feature steps follow RED/GREEN/REFACTOR; Task steps follow Scope/Tooling/Do/Verify/Document.
Steps build strictly on their predecessors with no orphaned code.

Read `spec.md` in full before starting.
The source of truth is the `## Architecture` (Exercises, Observability, Documentation), `## Exercise requirements`, `## Observability requirements`, `## Test requirements`, and `## Documentation requirements` sections, with the live mechanics and the owner's rulings in `## Starting context`.
Honor the fences in `## Invariants`, `## Non-goals`, and both `**Deferred:**` lists: one mechanism only (a blocked event loop), no slot-sizing, heartbeat-tuning, timeout-tuning, or retry-policy lesson, no load test or benchmark, no flood on more than two Workers or faster than 10 receipts per second, no loop-lag canary, no alert rules, no committed whole-run capture script, no Web UI screenshots beyond exercise 02, no new Python runtime dependency, and a frozen root package.

The order of work is fixed by what each step needs from the one before it.
The observability change comes first because it is small and the captures depend on it.
The exercise 06 code comes next: the solution copy, then the flood starter, then the practice copy.
The receipt-gap helper changes after the practice copy exists, because its test fixtures are real histories from a two-Worker flood of that copy, and before the captures, because the captures quote its output.
Housekeeping lands before the captures so no capture is taken of code that then changes.
All prose comes after the captures, and no prose step invents output.

## Current Status

- [ ] Section 1: Observability For Two Workers
  - [ ] Step 1: Third Scrape Target And The Per-Worker Panel
- [ ] Section 2: Exercise 06 Code
  - [ ] Step 2: Exercise 06 Solution Copy With The Lock And The Lookup
  - [ ] Step 3: The Flood Starter
  - [ ] Step 4: Exercise 06 Practice Copy And Gate Integration
- [ ] Section 3: Receipt-Gap Helper
  - [ ] Step 5: Identity View For The Receipt-Gap Helper
- [ ] Section 4: Housekeeping
  - [ ] Step 6: Review Findings With No Behavior Change (task)
- [ ] Section 5: Live Captures
  - [ ] Step 7: Capture Exercise 06 On Two Workers (task)
  - [ ] Step 8: Capture Exercise 03 And The Root Reference Readings (task)
- [ ] Section 6: Shared Recognition Block
  - [ ] Step 9: Recognition Block And Teaching-Code Note (task)
- [ ] Section 7: Exercise READMEs
  - [ ] Step 10: Exercise 06 README (task)
  - [ ] Step 11: Fold-Ins For Exercises 01 To 05 (task)
- [ ] Section 8: Series Drafts
  - [ ] Step 12: Draft Part 7 (task)
  - [ ] Step 13: Updates To Parts 1 To 6 (task)
- [ ] Section 9: Root Documentation Refresh
  - [ ] Step 14: README, CLAUDE.md, And The Drafts Index (task)
- [ ] Section 10: Review Handoff
  - [ ] Step 15: Decisions Record And The Pull Request Comment (task)

## Architecture Recap (target for this arc)

The repository keeps its four layers: the frozen root package, `exercises/`, `scripts/`, and `observability/`.
This arc adds one exercise, widens the helper and the dashboard so they work with two Workers, and folds four review items into the existing prose.

- Root package (`src/temporal_async_debug/`): unchanged.
  Only `tests/test_observability_config.py` and `tests/test_receipt_gaps.py` (with new fixtures under `tests/fixtures/`) change at the root.
- `exercises/06-finding-the-frozen-worker/{README.md,practice/,solution/}`: the same frozen loop as exercises 01 to 05, seen from a two-Worker fleet under steady receipt traffic.
  The reader finds the frozen Worker from the Event Histories before attaching any process tool.
- `scripts/receipt_gaps.py`: gains `--by-identity` and `--summary`.
  Its default output does not change by a byte.
- `observability/`: Prometheus scrapes a third target, `127.0.0.1:9466`, and the dashboard gains one per-Worker panel.
  The six existing panel expressions stay as they are.
- Prose: a shared recognition block in the root README and the primer, a teaching-code note, a single-Worker sentence in exercises 01 to 05 and parts 1 to 6, the exercise 06 README, and draft part 7.

| Exercise 06 | What it is |
|---|---|
| The bug | `get_location` is an `async def` Activity that reads a location cache through `sqlite3`, and the bad run's lookup waits on a database lock the starter holds |
| The failure | On two Workers under a flood of receipts, a few percent of receipts fail and a band of receipts runs slow; nothing names the cause |
| The tool | `just receipt-gaps --by-identity --summary` names the Worker identity that holds the Workflow Task timeouts, then `asyncio ps` and `py-spy dump` on that one process |
| The fix | `get_location` becomes a plain `def` Activity on a `ThreadPoolExecutor` sized to the Activity slots (the exercise 01 fix) |
| Part D test | A probe test holds the lock inside the test and fails while the lookup starves a 50 ms ticker |

Design decisions for exercise 06 that the steps below rely on (each is a build decision, listed for the owner in Step 15):

- `GeoEnrichmentInput` carries `location_cache_path: str | None = None` in place of exercise 01's `upstream_url`.
  When it is set, `get_location` looks the IP address up in the cache first, and on a miss it falls through to the geo providers.
  The cache table is empty, so the lookup always misses once the lock is released.
  No copy carries a hardcoded fallback city.
- `get_ip` stays `async def` with `httpx.AsyncClient` in both copies, so the `sqlite3` lookup is the practice copy's only blocker.
- `db_lock.py` exposes a context manager that yields a handle with the database path and an `arm()` method.
  The hold is counted from `arm()`, which the starter calls right after it submits the bad run.
- Both copies read `ASYNC_DEBUG_METRICS_PORT` exactly as exercise 03's solution does, and run on the SDK's default slot counts.
  The practice copy passes no `max_concurrent_activities`; the solution sets its constant to 100 so the executor is sized to it.
- The flood's one gate is the server-side check that the bad run's `get_location` is STARTED.
  The flood has no metrics-scrape gate.
- The flood's pure functions (the flood plan, the summary, the formatting) live in `flood.py`, which imports nothing from Temporal.
  `starter.py` imports them and keeps the parser, the freeze gate, and the flow.

## Section 1: Observability For Two Workers

**Tools:**
- Skills: python:python
- MCPs: none
- Linters: uv run ruff check --output-format=json ., uv run mypy .

Exercise 06 runs a second Worker whose metrics endpoint is `127.0.0.1:9466`.
Prometheus must scrape it, and the dashboard needs one panel that draws a line per Worker.

### Step 1: Third Scrape Target And The Per-Worker Panel

**NOTE**: `observability/prometheus.yml` lists two targets (9464 and 9465) and `observability/grafana/dashboards/async-debug.json` has six panels with ids 1 to 6.
`tests/test_observability_config.py` has `test_prometheus_scrapes_exactly_the_sdk_and_dev_server_endpoints`, which asserts the two targets and must change.
The per-Worker panel is worded as Workflow Tasks handed to a Worker that cannot complete them; it is no slot-sizing lesson.
The third target is always configured, so with one Worker it reads as down on the Prometheus targets page.
The READMEs say so in Step 14, not here.

```text
Add the third Prometheus target and the per-Worker dashboard panel, test first. Read spec.md "## Observability requirements" and the Observability part of "## Architecture" before starting.

1. RED: Write the config tests first:
   - Modify tests/test_observability_config.py:
     - Rename test_prometheus_scrapes_exactly_the_sdk_and_dev_server_endpoints to test_prometheus_scrapes_both_worker_endpoints_and_the_dev_server, and assert sorted(targets) == ["127.0.0.1:9464", "127.0.0.1:9465", "127.0.0.1:9466"].
     - Test that exactly one panel's expression is temporal_worker_task_slots_used{worker_type="WorkflowWorker", task_queue="async-debug-task-queue"}, that the expression is not wrapped in sum(...), and that its legend format is {{instance}}.
     - Test that the Task Queue name inside that expression equals TASK_QUEUE imported from temporal_async_debug.shared (parse the name out of the expression; do not hardcode it twice in the test).
     - Test that the six existing panel expressions are all still present, pinned as string literals in the test (copy them from the dashboard JSON as it stands before this step).
     - Test that panel ids are unique.
   - Run uv run pytest tests/test_observability_config.py and confirm the new tests fail for the right reason.

2. Document the config:
   - Update the header comment of observability/prometheus.yml to say it scrapes the SDK endpoint of the first Worker on 127.0.0.1:9464, the dev server on 127.0.0.1:9465, and a second Worker on 127.0.0.1:9466, and that the third target reads as down when no second Worker runs.

3. GREEN: Make the tests pass with the smallest change:
   - Add 127.0.0.1:9466 to the targets in observability/prometheus.yml.
   - Add one panel to observability/grafana/dashboards/async-debug.json: id 7, title "Workflow Task Slots Used Per Worker", gridPos h 8, w 24, x 0, y 24, the same datasource and field config as panel 5, the expression above, legend {{instance}}.
   - Give the panel a description in plain words: each line is one Worker, and a line that climbs and stays high is a Worker holding Workflow Tasks it cannot complete. Do not mention slot sizing or tuning.
   - Add temporal_worker_task_slots_used to ALLOWED_METRICS only if it is not there already.

4. RED: Add the integration check:
   - Confirm test_dashboard_panels_query_only_allowlisted_metrics still covers the new panel (it reads every panel expression). If the helper that extracts metric names does not handle a label selector with two labels, add a test for that case first.

5. GREEN: Fix the helper only if step 4 exposed a gap.

6. REFACTOR: Keep the dashboard JSON formatted as the file already is (same indent, same key order as panel 5). Do not touch panels 1 to 6.

7. Update documentation: none in this step. The root README's Observability section and CLAUDE.md change in Step 14.

8. Verify the per-Worker test fails if the expression is wrapped in sum by (worker_type), revert, then run just check.
```

## Section 2: Exercise 06 Code

**Tools:**
- Skills: python:python, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: just check-solutions, just check-practice

Exercise 06 follows the practice and solution layout of exercises 01 to 05.
Each copy is a flat set of modules plus `tests/`, with absolute top-level imports, and it runs from its own directory under the root virtual environment.
The solution copy is built first, with the bug in place long enough to prove the probe test has teeth.

### Step 2: Exercise 06 Solution Copy With The Lock And The Lookup

**NOTE**: Base the copy on `exercises/01-sync-http-client/solution/` (modules `activities.py`, `receipt.py`, `rollup.py`, `shared.py`, `worker.py`, `workflow.py`, and `tests/`).
Do not copy `slow_upstream.py` or `starter.py`; the flood starter is Step 3.
Take the metrics-port functions from `exercises/03-cpu-bound/solution/worker.py` (`resolve_metrics_port`, `build_telemetry_config`, `print_startup_banner`) and the six tests in `exercises/03-cpu-bound/solution/tests/test_metrics_port.py`.
A scratch spike of this exercise exists outside the repository; do not copy from it, because it carries a hardcoded fallback city and a synchronous `get_ip` that this exercise must not have.
`sqlite3` is in the standard library, so no dependency changes.

```text
Build exercises/06-finding-the-frozen-worker/solution/ test first. Read spec.md "## Architecture" (the exercise 06 bullet) and "## Exercise requirements" (exercise 06) before starting. Use flat top-level imports in every module (import shared, from activities import get_location).

1. RED: Create the solution copy and write its failing tests first:
   - Copy activities.py, receipt.py, rollup.py, shared.py, worker.py, workflow.py, and tests/conftest.py from exercises/01-sync-http-client/solution/ into exercises/06-finding-the-frozen-worker/solution/. Do not copy slow_upstream.py, starter.py, or the 01 tests that exercise the slow upstream.
   - In shared.py, replace GeoEnrichmentInput.upstream_url with location_cache_path: str | None = None, and update workflow.py so GeoEnrichmentWorkflow passes it to get_location. Remove UPSTREAM_TIMEOUT_SECONDS and every other trace of the slow upstream.
   - Create tests/test_db_lock.py for a module db_lock.py that does not exist yet:
     - Test that inside the context the database file lives under the directory passed in (use tmp_path) and holds a locations table with columns ip and location.
     - Test that before arm() is called, a second connection with timeout=0 raises sqlite3.OperationalError on SELECT (the lock is held).
     - Test that after arm() the lock is released once the delay has passed (use a delay of about 0.3 seconds and assert a second connection can SELECT afterwards).
     - Test that leaving the context without calling arm() releases the lock promptly (well under the delay).
   - Create tests/test_activities.py:
     - Test that get_location with location_cache_path=None asks the geo providers and returns their answer (network mocked with respx, as the 01 and 04 copies do).
     - Test that a cache hit returns the cached row and makes no HTTP call (the test creates a temporary database with one row).
     - Test that a cache miss falls through to the geo providers.
     - Keep the get_ip tests the 01 copy has, adapted to the async client.
   - Create tests/test_probe.py with test_get_location_does_not_starve_the_event_loop, following exercises/01-sync-http-client/solution/tests/test_probe.py: a 50 ms ticker task runs beside get_location in an ActivityEnvironment while the test itself holds the lock for about 0.6 seconds through db_lock with a tmp_path directory, and the test asserts the ticker kept ticking through the hold.
   - Create tests/test_metrics_port.py mirroring the six tests in exercises/03-cpu-bound/solution/tests/test_metrics_port.py.
   - Create tests/test_worker.py with test_worker_executor_has_a_thread_for_every_activity_slot, following exercises/04-zombie-thread/solution/tests/test_cancel_stops_work.py but asserting the executor's max_workers EQUALS max_concurrent_activities.

2. Document the components:
   - Write a module docstring for db_lock.py that says what the lock stands in for (a slow or contended synchronous database call) and that the hold is counted from arm().
   - Update the activities.py, shared.py, and worker.py module docstrings so they describe this exercise, not exercise 01.

3. GREEN: Write the code, bug first, then the fix:
   - Create db_lock.py: a context manager (for example hold_cache_lock(delay_seconds: float, directory: Path)) that starts a holder thread, and yields a small handle with the database path and an arm() method. The holder opens the file with sqlite3.connect(path, isolation_level=None), sets PRAGMA journal_mode=DELETE, creates the empty locations table (ip TEXT PRIMARY KEY, location TEXT), runs BEGIN EXCLUSIVE, waits until arm() or exit, then waits delay_seconds or until exit, then COMMITs. No module-level event; the handle owns its state. The context yields only after the lock is held.
   - Add a constant LOCK_WAIT_TIMEOUT_SECONDS = 120.0 in activities.py and a private lookup helper that connects with that timeout and runs SELECT location FROM locations WHERE ip = ?.
   - First write get_location as the practice copy will have it: async def, the synchronous sqlite3 lookup called directly, then httpx.AsyncClient for the providers. Run the probe test and confirm it FAILS. Record the failure output for the step report.
   - Then apply the fix: get_location becomes a plain def Activity (the sqlite3 lookup, then httpx.Client for the providers), get_ip stays async def with httpx.AsyncClient, and worker.py passes activity_executor=ThreadPoolExecutor(max_workers=MAX_CONCURRENT_ACTIVITIES) and max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES with MAX_CONCURRENT_ACTIVITIES = 100 and a plain comment that 100 is the SDK default and the executor is sized to it.
   - Put the three metrics-port functions from exercise 03's solution worker into worker.py unchanged in behavior (default port 9464, ASYNC_DEBUG_METRICS_PORT overrides it, the banner prints the bound port and the PID).
   - Confirm grep -rn "ANTIPATTERN" exercises/06-finding-the-frozen-worker/solution returns nothing.

4. RED: Add the Workflow-level test:
   - In tests/test_activities.py or a new tests/test_workflow.py, test with WorkflowEnvironment.start_time_skipping() and mocked Activities that GeoEnrichmentWorkflow passes location_cache_path through to get_location unchanged.

5. GREEN: Wire it up so that test passes, and confirm build_worker registers all three Workflow types and every Activity.

6. REFACTOR: Remove any name, comment, or docstring left over from exercise 01 (upstream, slow_upstream). Keep get_location's sqlite3 lookup in one small helper so the practice copy can differ from the solution in as few lines as possible.

7. Update documentation: none in this step. The exercise README is Step 10.

8. Verify the probe test has teeth: change get_location back to async def with the direct lookup, confirm test_get_location_does_not_starve_the_event_loop fails, restore the fix, then run just check. Use the temporal-docs MCP to confirm that activity_executor runs only def Activities before writing that into any comment.
```

### Step 3: The Flood Starter

**NOTE**: The flood replaces the small fleets of exercises 01 to 05.
It is steady traffic, about 10 receipts per second for about 50 seconds, never a burst.
The freeze gate is the function `wait_for_activity_started` in `exercises/01-sync-http-client/solution/starter.py`, which polls `handle.describe()` and looks for a pending Activity of the given type in state STARTED.
The flood plan and the summary are pure functions in their own module, `flood.py`, so they can be tested with no server and no Temporal import.
`starter.py` imports them and holds the parser, the freeze gate, and the flow.
The timeline line format matches the spike output the spec quotes: `submitted  -5s..  +0s n=50 failed=1 slow>2s=3 p50=0.37s max=9.81s`.

```text
Add flood.py and starter.py to exercises/06-finding-the-frozen-worker/solution/, test first. Read spec.md "## Exercise requirements" (the flood starter paragraphs of exercise 06) before starting.

1. RED: Write the pure-function and parser tests first:
   - Create exercises/06-finding-the-frozen-worker/solution/tests/test_flood.py (it imports from flood only):
     - Flood plan: test that flood_due_times(rate=10, duration_seconds=50) returns 500 offsets, starts at 0.0, and spaces them 0.1 seconds apart; test that planned_duration(lead=10, block_seconds=30, tail=10) is 50; test a rate of 4 over 2.5 seconds gives 10 offsets.
     - Summary bucketing: given hand-built ReceiptRecord values and a freeze offset, test that a receipt submitted 3 seconds before the freeze lands in the -5s..+0s bucket, that one submitted exactly at the freeze lands in +0s..+5s, that failed counts and slower-than-2-seconds counts are per bucket, that the median and the slowest are per bucket, and that an empty bucket between the first and the last is still returned with a count of 0.
     - Summary totals: test that the totals report receipts submitted, how many failed, and the first failure's message, and that a run with no failure reports none.
     - Formatting: test one formatted bucket line against an exact expected string, and one empty bucket line.
   - Create exercises/06-finding-the-frozen-worker/solution/tests/test_starter.py:
     - Argument parsing: test the defaults (--rate 10, --lead 10, --block-seconds 30, --tail 10, --bad 1, --rollups 1), test --bad 0, and test that a rate of 0 or below and a negative --bad are rejected.
     - Freeze gate: test wait_for_activity_started against a mocked handle whose describe() reports the Activity STARTED (returns True), reports it SCHEDULED only (keeps polling, then returns False at the timeout), and reports no pending Activity (returns False). Patch the sleep so the test does not wait.
   - Run the tests and confirm they fail because flood.py and starter.py do not exist.

2. Document the component:
   - Write the flood.py module docstring: the flood plan and the closing summary as pure functions, with no I/O and no Temporal import.
   - Write the starter.py module docstring: what the flood is (steady receipt traffic on the one Task Queue, with one bad geo run in the middle), what --bad 0 does (the healthy flood: same stream, same length, no lock held), and what the closing summary prints.

3. GREEN: Write the minimal code:
   - flood.py, pure functions: due_time(index, rate), flood_due_times(rate, duration_seconds), planned_duration(lead, block_seconds, tail), a frozen ReceiptRecord dataclass (submit_offset, latency_seconds, failed, failure_message), a frozen Bucket dataclass, summarize(records, freeze_offset) with 5-second buckets indexed by floor((submit_offset - freeze_offset) / 5) and a slow threshold of 2 seconds, and format_summary(...) returning lines.
   - starter.py: build_parser with the six flags above.
   - starter.py: wait_for_activity_started, carried over from exercises/01-sync-http-client/solution/starter.py.

4. RED: Add the flow test:
   - In tests/test_starter.py, test the main flow with a fake client object (no server): with --bad 0 the starter never enters db_lock and submits exactly the planned receipts; with --bad 1 it submits the rollup, then the bad run with location_cache_path set to the lock's database path, calls arm() after the submit, and calls the gate with activity type "get_location". Use a short lead, block, and tail and a patched clock or sleep so the test runs fast.

5. GREEN: Wire up the flow in starter.py, importing the plan and the summary from flood:
   - A producer task submits one OrderReceiptWorkflow at each due time and records its result or failure as a ReceiptRecord; a failed Workflow never aborts the flood.
   - After --lead seconds: start --rollups rollups, wait 1 second, start --bad bad geo runs with the cache path, call arm(), then wait_for_activity_started(bad[0], "get_location", 20 seconds). Record the freeze offset when the gate returns True. If it returns False, print one line saying the freeze was not confirmed and use the submit time of the bad run as the zero point.
   - Bad flood: keep producing at the same spacing until --tail seconds after the bad runs return. Healthy flood (--bad 0): produce exactly flood_due_times(rate, planned_duration(...)) with no lock held, and use the end of the lead as the zero point of the timeline.
   - Print the closing summary only (no line per Workflow): receipts submitted, how many failed, the first failure's message, the outcome of each rollup and each bad run, then the timeline. Exit with os._exit(0) as the other starters do.

6. REFACTOR: Keep flood.py free of I/O and of any temporalio import, and keep starter.py free of bucketing or formatting logic. No name in either module labels a role (no "victim", no "bystander" in identifiers).

7. Update documentation: none in this step.

8. Verify the bucketing tests fail if the bucket width constant changes from 5 to 10, revert, then run just check. Then run one live smoke check (not a capture): just server in one terminal, one Worker from the solution directory, uv run python starter.py --bad 0 --lead 2 --block-seconds 2 --tail 2, and confirm the summary prints with no failure. Stop the server and the Worker by their recorded PIDs. If the smoke check cannot run, report a Failure; do not skip it silently.
```

### Step 4: Exercise 06 Practice Copy And Gate Integration

**NOTE**: The practice copy is the solution copy before the fix, with the antipattern marker and the `# TODO PART X:` comments.
`flood.py`, `starter.py`, and `db_lock.py` are identical in both copies.
The justfile needs no change: `just check` already loops over every `exercises/*/solution`, and `just check-practice` over every `exercises/*/practice`.
The marker must have the exact greppable form in CLAUDE.md.

```text
Create exercises/06-finding-the-frozen-worker/practice/ from the solution copy.

1. RED: Write the practice test stub first:
   - Copy the whole solution directory to exercises/06-finding-the-frozen-worker/practice/.
   - In practice/tests/, keep conftest.py and test_metrics_port.py, delete test_activities.py, test_db_lock.py, test_flood.py, test_starter.py, test_worker.py, and any Workflow test, and replace test_probe.py with a stub: the imports the reader will need, a "# TODO PART D:" comment that says to write a test that runs get_location beside a ticker while the test holds the cache lock, and a body of pytest.fail("TODO PART D: write the probe test").

2. Document the components:
   - Update the practice module docstrings where they describe the fix (they must describe the code as it is in practice, with the blocker in place).

3. GREEN: Put the bug back:
   - practice/activities.py: get_location is async def, calls the synchronous sqlite3 lookup directly, then uses httpx.AsyncClient for the providers. On the line above the lookup call, add exactly:
     # ANTIPATTERN (deliberate, for teaching): sqlite3 is a synchronous driver, so this query blocks the Worker's event loop while it waits on the database lock. Correct: make this a plain def Activity and run it on the Worker's ThreadPoolExecutor. Do not copy.
   - Add "# TODO PART C:" at the lookup call, naming what to look for without giving the answer, and "# TODO PART D:" at the get_location signature.
   - practice/worker.py: no activity_executor and no max_concurrent_activities argument (the SDK defaults apply), with a "# TODO PART D:" comment where the executor argument belongs. Keep the metrics-port functions as they are in the solution.

4. RED: Check the gate sees both copies:
   - Run just check-practice and just check-solutions and confirm each loop visits exercises/06-finding-the-frozen-worker.

5. GREEN: Fix any ruff or mypy finding in the practice copy without removing the bug or the marker.

6. REFACTOR: Run diff -r on the two copies. The difference must be limited to the get_location form, the Worker's executor arguments, the marker, the TODO comments, the docstring lines that describe them, and the tests directory. Remove any other drift.

7. Update documentation: none in this step.

8. Verify: grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/06-finding-the-frozen-worker/practice returns exactly one line, the same grep over exercises/*/solution returns nothing, then run just check and just check-practice.
```

## Section 3: Receipt-Gap Helper

**Tools:**
- Skills: python:python
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: uv run ruff check --output-format=json ., uv run mypy .

With two Workers, the helper's default lines name no Worker.
The identity view groups the same histories by the identity on their Started events, which is the step that names the frozen process.

### Step 5: Identity View For The Receipt-Gap Helper

**NOTE**: `scripts/receipt_gaps.py` is 118 lines, standard library only, read-only, and sequential (518 histories took 37.7 seconds in the fleet check, so it needs no thread pool).
`tests/test_receipt_gaps.py` tests it against fixtures in `tests/fixtures/` (`receipt-gaps.txt`, `receipt-healthy.json`, `receipt-no-activity.json`, `receipt-timed-out.json`).
The new fixtures are real histories from a two-Worker bad flood of the exercise 06 practice copy, so this step runs live processes before it writes a test.
Every occurrence of the machine's hostname in a committed fixture is replaced with the word `host` (identity fields and sticky Task Queue names included).
The hostname is a short string that also appears inside ordinary words, so check the masked files by eye; a blind search and replace over the JSON is not safe.
A retried Activity's history keeps only its last attempt's `ActivityTaskStarted`, so an attempt swallowed by the frozen Worker and retried elsewhere is not counted; the code comment and the README (Step 10) say so.

```text
Add --by-identity and --summary to scripts/receipt_gaps.py, test first, with fixtures captured from a live flood. Read spec.md "## Architecture" (the helper identity view) and the fleet tests in "## Test requirements" before starting.

1. RED: Capture the fixtures, then write the failing tests:
   - Start a fresh dev server (just server). Start two Workers from exercises/06-finding-the-frozen-worker/practice: uv run python worker.py, and ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py. Record all three PIDs.
   - From the practice directory run uv run python starter.py (the bad flood, defaults). Save the summary to the scratchpad. If no receipt fails and no Workflow Task times out, stop with a Failure; do not invent a history.
   - Save temporal workflow show --output json for: one healthy receipt; one receipt whose first Workflow Task timed out and completed on a retry (prefer one whose retry ran on the other identity); one failed receipt whose Activity timed out; and, if the run has one, a Workflow with a timeout on a Workflow Task after the first. Stop the Workers and the server by PID.
   - Mask the hostname in each saved file to the word host, check each file by eye, and commit them as tests/fixtures/fleet-receipt-healthy.json, fleet-receipt-retried.json, fleet-receipt-failed.json, and (if captured) fleet-later-timeout.json. If no later-timeout history was captured, build that one case inside the test from a captured history and name the test so it says the history is derived.
   - Modify tests/test_receipt_gaps.py:
     - Test that the default output for the existing fixtures still equals tests/fixtures/receipt-gaps.txt byte for byte (keep the existing test; add one for main() called with no new flag).
     - Test that with --by-identity a healthy receipt's line also prints the identity from its first WorkflowTaskStarted and from its ActivityTaskStarted with the attempt number.
     - Test that for the retried receipt the line prints both identities when they differ, and the attempt from the WorkflowTaskScheduled that completed the first Workflow Task.
     - Test that a WorkflowTaskTimedOut is attributed to the identity on the WorkflowTaskStarted before it, for the first Workflow Task and for a later one.
     - Test that the failed receipt's timed-out Activity is marked on its line and attributed through the ActivityTaskStarted that shares its scheduled event id.
     - Test the per-identity summary lines: first Workflow Tasks started, Workflow Task timeouts held, Activities failed on it, largest WT1.
     - Test that --summary with --by-identity prints the summary lines alone, and that --summary without --by-identity is rejected with a clear message.

2. Document the component:
   - Update the module docstring: fix the line that says "Run it from the repository root, or from any exercise directory with the path adjusted:" so it describes how just receipt-gaps runs the script, and describe the two flags and the retried-Activity limit.

3. GREEN: Write the minimal code:
   - Add the two flags to main's parser. Keep format_history's default output path untouched; add the identity fields behind the flag.
   - Add a small pure function that reduces one history to its identity facts, and a pure function that folds those facts into per-identity summary lines.

4. RED: Add the end-to-end test:
   - Test main() with a fake runner that serves the fixtures by Workflow ID and a list call, with --limit, --by-identity, and --summary, and assert the exact emitted lines.

5. GREEN: Wire the flags through main and receipt_ids. The script stays standard library only, read-only, and sequential.

6. REFACTOR: Keep the module readable top to bottom: types, history readers, formatters, main. No function longer than it needs to be; full type hints; Google-style docstrings on the public functions.

7. Update documentation: none beyond the docstring. The README row for just receipt-gaps changes in Step 14.

8. Verify the default-output test fails if a default line gains a field, revert, then run just check. Run a privacy check as its own command: search the new fixtures for the machine's hostname and read every matching line by eye.
```

## Section 4: Housekeeping

**Tools:**
- Skills: python:python
- MCPs: none
- Linters: uv run ruff check --output-format=json ., just check-solutions, just check-practice

### Step 6: Review Findings With No Behavior Change (task)

**NOTE**: These are the info-level findings left over from the previous arc's validator passes.
Check each one against the code before changing anything; if a finding no longer applies, leave the code alone and say so in the step report.
No item changes behavior, so no capture taken before this step goes stale, and no test should need a new assertion.

```text
1. Scope:
   - Artifact(s): exercises/03-cpu-bound/solution/worker.py, exercises/05-catching-blockers-early/{practice,solution}/shared.py, exercises/05-catching-blockers-early/solution/tests/test_probe_all_activities.py, the test files that call a private _job_is_done, justfile, exercises/01-sync-http-client/practice/ (TODO comments) and exercises/01-sync-http-client/README.md.
   - Desired end state: each finding below is either fixed with no behavior change or recorded as not applicable, and the gate is green.

2. Tooling:
   - Skills: python:python
   - MCPs: none
   - External: just, grep

3. Do the work:
   - exercises/03-cpu-bound/solution/worker.py near line 160: the metrics port is resolved twice (once for telemetry, once for the banner). Resolve it once and pass it to both.
   - exercises/05-catching-blockers-early/solution/tests/test_probe_all_activities.py near line 49: the docstring's stall figure disagrees with the measured one (0.6 s against 1.1 s). Read the exercise 05 README's captured figure and make the docstring agree with it, or remove the figure.
   - exercises/05-catching-blockers-early/{practice,solution}/shared.py near line 20: the PAYLOAD_RECORDS comment gives 340 ms where the README's capture gives about 350 ms. Make the comment agree with the README in both copies.
   - Tests that call a private _job_is_done: if the function has a public caller the test can go through, test through that; otherwise leave the call and add nothing.
   - justfile lines 14 to 16: the comment above check-solutions runs long. Rewrap it into short lines. Keep the default recipe first.
   - exercises/01-sync-http-client/practice: the TODO comments use "TODO PART C" where the README's matching part is Part D. Read the README's parts and make the comment letters match the README; change comments only. Update the README's line that names the TODO letters if it disagrees.

4. Verify:
   - just check && just check-practice exits 0, and git diff shows comment, docstring, and single-resolution changes only.

5. Document:
   - none in committed prose. List in the step report which findings were fixed and which did not apply.
```

## Section 5: Live Captures

**Tools:** none

Both steps are live and manual, and they commit no code.
Captures land in the scratchpad at `/tmp/claude-1000/-home-mmegger-Code-MasonEgger-temporal-async-debug/10fd033c-1cfd-409b-a456-989de32d14dd/scratchpad/captures/`, and Grafana panel images land under `docs/images/`.
The scratchpad already holds the capture conventions from the previous arc: `captures/INDEX.md` maps each capture file to its exercise, state, and tool, `captures/FINDINGS.md` records what disagreed with the spec, and `shot.py` takes panel images with Playwright through `uv run --with playwright`.
Use the dev server single binary (`just server`), never a self-hosted cluster, and never attempt sudo.
Stop every process by its recorded PID.
Scratchpad logs hold the real hostname, and some hold a public IP address; none of that goes into a committed file.

### Step 7: Capture Exercise 06 On Two Workers (task)

**NOTE**: Each of the three floods runs on a freshly started dev server, because one slow run in the fleet checks was the fourth of five back-to-back floods on one server.
The dashboard and Web UI readings are taken during the freeze as well as after it, with the time of each reading written down.
If a receipt fails or stalls after the fix, the build stops here and `spec.md` is corrected before any README is written.

```text
1. Scope:
   - Artifact(s): scratchpad captures/06-*/ files, captures/INDEX.md, captures/FINDINGS.md, and docs/images/06-practice-frozen-per-worker-slots.png and docs/images/06-solution-live-per-worker-slots.png (plus the other panels named below).
   - Desired end state: one healthy flood and one bad flood of the practice copy and one bad flood of the solution copy, each on two Workers and a fresh dev server, with every tool reading in spec.md "The tools in a fleet" saved to a file and indexed.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: temporal CLI (just server), just metrics, uvx py-spy, python -m asyncio ps and pstree, top, curl, just receipt-gaps, the scratchpad shot.py pattern.

3. Do the work:
   - Start just metrics once. For each flood below: start a fresh just server, start two Workers from the named copy (the second with ASYNC_DEBUG_METRICS_PORT=9466), each with its log saved to its own file, and record the PIDs.
   - Flood A, healthy, practice copy: uv run python starter.py --bad 0. Save the summary and both Worker logs. If the slowest receipt is over about 1 second, note it in FINDINGS.md (the README then tells the reader to lower --rate).
   - Flood B, bad, practice copy: uv run python starter.py. During the freeze, and with a timestamp on each reading, save: python -m asyncio ps and pstree for each Worker PID, uvx py-spy dump for each PID, top -b -n 1 for both PIDs, temporal task-queue describe, a curl of each metrics endpoint with its response time, the per-Worker slot gauge from each endpoint, and the Web UI's Task Queue and Workers pages as text or a note of what they show (no screenshot is committed). After the thaw save: the starter summary, both Worker logs, just receipt-gaps --limit 600 (default view), just receipt-gaps --limit 600 --by-identity, just receipt-gaps --limit 600 --by-identity --summary, and temporal workflow show for one failed receipt, one stalled receipt, the rollup, and the bad geo run.
   - Take the dashboard images for flood B with a time window that starts at the flood start: the per-Worker panel, the slots panel, the failures panel, and the two Workflow Task latency panels, named docs/images/06-practice-frozen-<panel>.png.
   - Flood C, bad, solution copy: uv run python starter.py. Save the summary, both logs, uvx py-spy dump of the Worker that ran get_location (find it with just receipt-gaps --by-identity), the three receipt-gaps views, and the same panels as docs/images/06-solution-live-<panel>.png.
   - Stop-and-correct rule: if flood C shows a failed receipt, a Workflow Task timeout, or a receipt slower than 2 seconds, rerun it once on another fresh server. If it happens again, stop with a Failure and name the readings; spec.md must be corrected before the README is written.
   - Mask identities in every excerpt meant for prose with sed -E 's/@[A-Za-z0-9._-]+/@host/g', and write the masked excerpts beside the raw files. Add every file to captures/INDEX.md. Record in FINDINGS.md every figure that falls outside the ranges spec.md quotes, and whether TMPRL1101 and "Task not found when completing" appear in either Worker log.

4. Verify:
   - Every tool listed in spec.md "The tools in a fleet" has a file in INDEX.md for flood B; flood A reports 0 failed; flood B reports failed receipts and the --by-identity --summary output puts every Workflow Task timeout on one identity; the docs/images/06-*.png files exist and show data. A search of docs/images/ and the masked excerpts finds no hostname.

5. Document:
   - captures/INDEX.md and captures/FINDINGS.md in the scratchpad. Commit only the PNG files under docs/images/.
```

### Step 8: Capture Exercise 03 And The Root Reference Readings (task)

**NOTE**: Exercise 03's two-Worker step changes from `--bad 3` to `--bad 4`, and its single-Worker step runs `--bad 2`, so both need captures with the per-identity placement saved.
The recognition block quotes "Task not found when completing" from the root `just block` Worker log, and may say that a healthy run prints none only if a fresh healthy-only root Worker log shows it.
Three smaller readings ride along because they need the same running stack.

```text
1. Scope:
   - Artifact(s): scratchpad captures/03-rework2/, captures/root-rework2/, captures/02-rework2/, captures/INDEX.md, captures/FINDINGS.md, and docs/images/02-solution-live-*.png (replaced).
   - Desired end state: every figure Steps 9, 11, 13, and 14 will quote has a saved, indexed source.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: temporal CLI, just, uvx py-spy, top, sysctl (read only), the scratchpad shot.py pattern.

3. Do the work:
   - Exercise 03, solution copy, one Worker: uv run python starter.py --bad 2 --geo 0 --rollups 0 --receipts 0. Save the starter output, top for the Worker, the run times from temporal workflow describe for each run, and which identity ran each get_location (from each history's ActivityTaskStarted).
   - Exercise 03, solution copy, two Workers (the second with ASYNC_DEBUG_METRICS_PORT=9466): the same command with --bad 4. Save the same readings, top for both Workers, and the per-identity placement counts. Record the machine's load average beside the timings.
   - Root package, fresh server and fresh Worker with its log saved: run just healthy only. Save the Worker log and count the lines that contain "Task not found when completing" (the expected count is 0; record what the log shows).
   - Root package, fresh server and fresh Worker: run just block. Save the Worker log, the "Task not found when completing" lines with their times relative to the thaw, and the Workflow Task latency panel's peak reading for the run (the README quotes a 29-second stall reading as 5 to 6 seconds; record what this run shows).
   - Exercise 02, solution copy: rerun the solution fleet and retake the four 02-solution-live panel images with a window that starts at the fleet start. Replace the PNG files under docs/images/ with the same file names.
   - Save the output of sysctl kernel.yama.ptrace_scope (the read only; never the sudo write).
   - Mask identities in excerpts, index every file, and record in FINDINGS.md every figure that differs from what the READMEs and spec.md quote today.

4. Verify:
   - INDEX.md has an entry for each reading above; the exercise 03 placement counts add up to 2 and 4; the four replaced PNG files show a window that begins at the fleet start.

5. Document:
   - captures/INDEX.md and captures/FINDINGS.md in the scratchpad. Commit only the replaced PNG files.
```

## Section 6: Shared Recognition Block

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: just lint-prose README.md docs/drafts/event-loop-primer.md, just lint-keyboard README.md docs/drafts/event-loop-primer.md

Every prose step in Sections 6 to 9 follows the same order: invoke content-design:tutorial-writing, then voice:teaching, then draft, then run content-design:review-content.
`just preflight` must exit 0 before any prose is written; a non-zero exit is a Failure, not a reason to skip linting.
Never invent output: every quoted block is a mechanical splice of a capture indexed in the scratchpad `captures/INDEX.md`, and every trim is disclosed in one active sentence.
Flag a missing capture with `<CLAUDE_HELP>` tags and go on with the rest.
The validator maps a Vale `error` to block, a `warning` to warn, and a `suggestion` to info, and every keyboard-characters hit is a block.
The voice:teaching skill says every draft waits for the owner's eyes; the owner reviews once after the build, so do not read that rule as a reason to abort or to skip a step.

### Step 9: Recognition Block And Teaching-Code Note (task)

**NOTE**: The block answers "how do I recognize this in my own system?" in one place, so each exercise can link to it in one line.
`TMPRL1101` is named in prose only, as a line that depends on timing, with a pointer to exercise 02; the block does not lead with it.
The teaching-code note is written once, in the repository's own words, beside the README's statement that the code is deliberately broken; it names no course and no organization.

```text
1. Scope:
   - Artifact(s): README.md, docs/drafts/event-loop-primer.md, docs/drafts/smell-reports.md.
   - Desired end state: the root README carries the recognition block and the teaching-code note, and the primer's "What a frozen loop looks like from outside" section carries the same symptom list and links to the README's capture.

2. Tooling:
   - Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
   - External: just preflight, just lint-prose, just lint-keyboard

3. Do the work:
   - Run just preflight and stop with a Failure if it exits non-zero.
   - README.md: add the teaching-code note next to the warning near the top (line 5): the code is written to teach, so settings and shapes are altered to make one point visible, and exercises 01 to 05 run a single Worker with two Activity slots so one blocking call fails loudly, where a real fleet masks it (exercise 06).
   - README.md: add a section with a stable anchor (for example "## Recognizing a blocked event loop") holding the symptom list from spec.md "## Documentation requirements": Workflow Task timeouts on Workflows whose code is fine; Workers that stay alive and stay listed as pollers but stop completing work; an Activity marked Started long before its code runs; the Worker log line "Task not found when completing"; and TMPRL1101. Follow the list with the code question: are these Activities async def, and what do they call?
   - Quote "Task not found when completing" from the root just block Worker log captured in Step 8, as a trimmed block, and say the Worker prints it at the thaw. Write "a healthy run prints none" only if Step 8's healthy-only log showed a count of 0.
   - Name TMPRL1101 in a sentence, say it depends on timing, and link to exercise 02.
   - docs/drafts/event-loop-primer.md: put the same symptom list and the code question in the "What a frozen loop looks like from outside" section, in the primer's sentence-case style, and link to the README section for the captured log line. Add one sentence under "Getting blocking work off the loop" saying that activity_executor runs only def Activities (check it against the temporal-docs MCP first).
   - Add a short entry for this change to docs/drafts/smell-reports.md only if a new smell or open point came up; otherwise leave the file alone.
   - Run content-design:review-content on both files and fix what it finds.

4. Verify:
   - just lint-keyboard README.md docs/drafts/event-loop-primer.md exits 0, and just lint-prose on the same files shows no new error or warning against the count before the step.

5. Document:
   - none beyond the two files.
```

## Section 7: Exercise READMEs

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: just lint-prose exercises/*/README.md, just lint-keyboard exercises/*/README.md

The prose rules at the top of Section 6 apply to both steps.
Exercise READMEs use sentence case headings and the part structure of exercises 01 to 05 (a "During this exercise, you will" list, Prerequisites, Parts A to E, Conclusion, "This is the end of the exercise.").

### Step 10: Exercise 06 README (task)

**NOTE**: The README opens with the contrast to exercises 01 to 05 in the owner's framing: a failure this easy to see would be welcome in production, but more Workers mask it.
It quotes only its own captures from Step 7 and never writes "always"; which Worker freezes varies by run, so the README never names one in advance.
The rollup failed in two of six spike floods, so the README promises neither outcome and reports what its own capture shows.
`TMPRL1101` appeared in no spike flood, so the README does not list it as a symptom of this exercise unless Step 7's logs show it.
One sentence on the inferred cause of the failures is allowed, marked as inferred; it must not become a slot lesson.

```text
1. Scope:
   - Artifact(s): exercises/06-finding-the-frozen-worker/README.md, docs/drafts/smell-reports.md.
   - Desired end state: a reader with a clone, the Temporal CLI, and uv can follow Parts A to E on two Workers and find the frozen Worker from the histories.

2. Tooling:
   - Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
   - External: just preflight, just lint-prose, just lint-keyboard, the scratchpad build_readmes.py pattern for splicing captures

3. Do the work:
   - Run just preflight and stop with a Failure if it exits non-zero. Read spec.md "## Exercise requirements" for exercise 06 in full, and captures/INDEX.md and captures/FINDINGS.md from Step 7.
   - Opening: the "During this exercise, you will" list, the contrast with exercises 01 to 05, and the note that the second Worker runs with ASYNC_DEBUG_METRICS_PORT=9466 from the same directory.
   - Part A: run the healthy flood (--bad 0) and read its summary, then the bad flood, on two Workers. Read the bad flood's summary as an operator would: a few percent failed, a band of slow receipts in the timeline, and the failures stop before the freeze does. Quote the capture's summary and timeline.
   - Part B: link to the root README's recognition block in one line at the top. Run just receipt-gaps --by-identity --summary and read which identity holds every Workflow Task timeout and failed Activity. Show where that identity appears in a history: on the WorkflowTaskStarted before each WorkflowTaskTimedOut, on the ActivityTaskStarted of each timed-out receipt Activity, and on the bad run's ActivityTaskStarted for get_location. Read the PID out of PID@host, then run asyncio ps and py-spy dump on that process only. Compare the two Worker logs.
   - Part B, "The tools in a fleet": go through each tool in the spec's list with this capture's reading and say plainly which ones separate the frozen Worker from the healthy one and which do not (CPU does not, the Task Queue page does not, the default receipt-gaps view names no identity, the per-Worker panel does). State that a slow receipt on the healthy identity is not a second sick Worker, and that a retried Activity's history keeps only its last attempt's Started event.
   - Part B, production note (general practice, no capture): group Workflow Task and Activity timeouts by time window and by the Worker identity on their Started events; the default identity is PID@hostname, and on Kubernetes the hostname is the pod name; py-spy and asyncio ps in a pod need the SYS_PTRACE capability. One sentence that more Workers mask more, with no capture.
   - Part C: find the sqlite3 call in get_location and say why a synchronous driver blocks the loop.
   - Part D: write the probe test, then apply the exercise 01 fix (a def Activity on a ThreadPoolExecutor sized to the Activity slots). Say that activity_executor runs only def Activities.
   - Part E: rerun the bad flood on two Workers, and read the summary and the per-identity view again. Quote the after-fix capture, including the py-spy dump that shows the lookup on an executor thread.
   - Add an H2 section for this README to docs/drafts/smell-reports.md with the voice:teaching smell report. Any open point becomes a build decision recorded there, not a question that blocks the step.
   - Run content-design:review-content and fix what it finds.

4. Verify:
   - just lint-keyboard and just lint-prose on the README show no error; every quoted block traces to a file in captures/INDEX.md; a search of the README finds no hostname and no "always"; grep -c "TODO PART" matches the practice copy's comment letters.

5. Document:
   - docs/drafts/smell-reports.md gains the section above.
```

### Step 11: Fold-Ins For Exercises 01 To 05 (task)

**NOTE**: These are the review fold-ins the owner chose on November 9, 2026, plus the lines every exercise needs now that exercise 06 exists.
Exercise 03's second Worker moves from an optional section into the main fix path, framed as GIL isolation and never as fleet sizing.
Figures for exercise 03 come from Step 8's captures; placement is stated with counts from the capture, and no even split is promised.

```text
1. Scope:
   - Artifact(s): exercises/01-sync-http-client/README.md, exercises/02-sleep-between-heartbeats/README.md, exercises/03-cpu-bound/README.md, exercises/04-zombie-thread/README.md, exercises/05-catching-blockers-early/README.md.
   - Desired end state: each README carries the single-Worker sentence and the Part B link, and exercises 01, 02, 03, and 05 carry their fold-ins.

2. Tooling:
   - Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
   - External: just preflight, just lint-prose, just lint-keyboard

3. Do the work:
   - Run just preflight and stop with a Failure if it exits non-zero.
   - All five: after the "During this exercise, you will" list, add the single-Worker sentence (this exercise runs one Worker with two Activity slots so the failure is loud; exercise 06 shows the same bug on a fleet). At the top of Part B, add one line linking to the root README's recognition block.
   - Exercise 01: at the end of Part C, add the "same bug, other library" table. Each row names a category and a call shape, and a Python package only where the package name is not also a company name; the LLM-client row stays generic. In Part D, state that activity_executor runs only def Activities, so an async def Activity stays on the loop whatever executor the Worker has.
   - Exercise 02: in Part C, add the heartbeat sentence from spec.md (a heartbeat call inside a blocked loop is not sent until the loop runs again).
   - Exercise 03: move the second-Worker section out of "Optional" and into Part E's main path. The single-Worker step runs --bad 2 and the two-Worker step runs --bad 4 (replace the --bad 3 commands and prose near lines 488 to 502). Quote Step 8's timings and placement counts. Add one sentence that the figures depend on the reader's CPU.
   - Exercise 05: where the Workflow Task panels are near empty, keep the images and add one sentence saying why (a stall of about 350 ms on a 30-second rate average).
   - Leave the receipt-gap blocks in exercises 01 and 04 as they are.
   - Run content-design:review-content on the five files and fix what it finds.

4. Verify:
   - just lint-keyboard exercises/*/README.md exits 0; just lint-prose on the five files shows no new error or warning; grep -c "bad 3" exercises/03-cpu-bound/README.md is 0; each README links to the recognition block.

5. Document:
   - none beyond the five files.
```

## Section 8: Series Drafts

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
- MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
- Linters: just lint-prose docs/drafts/part-*.md, just lint-keyboard docs/drafts/part-*.md

The prose rules at the top of Section 6 apply.
A draft has a Title H1, an Introduction H3, a Prerequisites H2, "Step N: Gerund phrase" H2 sections, and a Conclusion H2, with no frontmatter and `TODO` cross-links between parts.
`docs/drafts/tutorial-original-draft.md` is provenance and is never edited or linted.

### Step 12: Draft Part 7 (task)

**NOTE**: Part 7 is the tutorial form of exercise 06, written from the exercise README and the same captures.
The per-Worker panel is named here and in the exercise 06 README only, as corroboration after the histories have named the Worker.

```text
1. Scope:
   - Artifact(s): docs/drafts/part-7-finding-the-frozen-worker.md, docs/drafts/smell-reports.md.
   - Desired end state: a seventh draft in the same structure and voice as parts 1 to 6, Vale-clean.

2. Tooling:
   - Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
   - External: just preflight, just lint-prose, just lint-keyboard, the scratchpad build_drafts.py pattern

3. Do the work:
   - Run just preflight and stop with a Failure if it exits non-zero. Read docs/drafts/part-6-catching-blockers-early.md for structure and voice, then exercises/06-finding-the-frozen-worker/README.md.
   - Write the draft: Introduction (the contrast with parts 1 to 6 and what the reader will be able to do), Prerequisites, then steps that follow Parts A to E (run the healthy and the bad flood, read the summary, group the histories by Worker identity, attach the process tools to the one process, find the call, write the probe test, apply the fix, rerun). Use the code sandwich for every block and quote only code that exists in the 06 copies and output from Step 7's captures.
   - Carry the production note and the per-Worker panel as corroboration. No slot lesson.
   - Use TODO cross-links for part 6 and the primer, as the other parts do.
   - Add an H2 section for part 7 to docs/drafts/smell-reports.md with the smell report; open points become recorded build decisions.
   - Run content-design:review-content and fix what it finds.

4. Verify:
   - just lint-keyboard docs/drafts/part-7-finding-the-frozen-worker.md exits 0 and just lint-prose on it shows no error or warning; every quoted block traces to captures/INDEX.md; no hostname in the file.

5. Document:
   - docs/drafts/smell-reports.md gains the section above.
```

### Step 13: Updates To Parts 1 To 6 (task)

**NOTE**: Parts 2, 3, and 4 mirror exercises 01, 02, and 03, so they take the same fold-ins as Step 11.
The twelve open `<CLAUDE_HELP>` tag pairs from the previous arc are replaced here with the build decisions listed under Implementation Guidelines: eleven in `docs/drafts/smell-reports.md` and one in `docs/drafts/part-1-healthy-worker.md` near lines 435 to 440.

```text
1. Scope:
   - Artifact(s): docs/drafts/part-1-healthy-worker.md through docs/drafts/part-6-catching-blockers-early.md, docs/drafts/smell-reports.md.
   - Desired end state: parts 1 to 6 agree with the exercise READMEs after Step 11, and no CLAUDE_HELP tag pair from the previous arc remains.

2. Tooling:
   - Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, temporal:temporal-developer
   - MCPs: mcp__temporal-docs__search_temporal_knowledge_sources
   - External: just preflight, just lint-prose, just lint-keyboard

3. Do the work:
   - Run just preflight and stop with a Failure if it exits non-zero.
   - Parts 1 to 6: add the single-Worker sentence in each Introduction, pointing forward to part 7 with a TODO cross-link.
   - Part 2: the "same bug, other library" table and the activity_executor statement, as in exercise 01's README.
   - Part 3: the heartbeat sentence, as in exercise 02's README.
   - Part 4: the second Worker as a required step with --bad 2 and --bad 4 and Step 8's figures, as in exercise 03's README.
   - Part 1: change the clone command near line 34 to https://github.com/MasonEgger/temporal-async-debug.git. Quote the captured output of the read-only sysctl kernel.yama.ptrace_scope from Step 8; keep the sudo sysctl write as a command with no output. Keep temporal task-queue describe as the reliable backlog reading. Replace the CLAUDE_HELP pair near lines 435 to 440 with the decided text.
   - docs/drafts/smell-reports.md: replace each of the eleven CLAUDE_HELP pairs with a line that starts "Build decision:" and states the decision from the Implementation Guidelines list. Update the sentence near line 6 that describes the tags. Never write that the owner ruled on a point the owner did not rule on.
   - Run content-design:review-content on the six parts and fix what it finds.

4. Verify:
   - grep -rn "CLAUDE_HELP" docs/drafts/part-*.md docs/drafts/smell-reports.md returns only tags added during this build (none from the previous arc); just lint-keyboard docs/drafts/part-*.md exits 0; just lint-prose on the six parts shows no new error or warning.

5. Document:
   - none beyond the files above.
```

## Section 9: Root Documentation Refresh

**Tools:**
- Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, content-design:style-linting
- MCPs: none
- Linters: just lint-prose, just lint-keyboard

### Step 14: README, CLAUDE.md, And The Drafts Index (task)

**NOTE**: The prose rules at the top of Section 6 apply.
`README.md` and `CLAUDE.md` use Title Case headings, and `MasonBase.Headings` and `MasonBase.SentenceCapitalization` hits in those two files are ruled false positives.
`README.md` line 18 holds a series-link `TODO` that waits on the owner's URL; leave it.

```text
1. Scope:
   - Artifact(s): README.md, CLAUDE.md, docs/drafts/README.md.
   - Desired end state: the three index documents describe the repository as it is after Steps 1 to 13, and the full prose set passes the linters and one final review-content pass.

2. Tooling:
   - Skills: content-design:tutorial-writing, voice:teaching, content-design:review-content, content-design:style-linting
   - MCPs: none
   - External: just preflight, just lint-prose, just lint-keyboard, just check, just check-practice

3. Do the work:
   - Run just preflight and stop with a Failure if it exits non-zero.
   - README.md: line 22 says the repository has three layers; make it four (root reference, exercises/, scripts/, observability/) to match CLAUDE.md. Add exercise 06 to the Exercises table. In the just receipt-gaps row, name --by-identity and --summary. In Observability, name the third target (127.0.0.1:9466, which reads as down when no second Worker runs) and the per-Worker panel. In "About the captured output", add ANSI stripping to the list of permitted edits. Update the ptrace note near line 723 to agree with part 1. If Step 8's root just block run showed a latency-panel reading other than the one the README quotes for the 29-second stall, correct the figure and name the run.
   - CLAUDE.md: list exercise 06 in the Layout section, describe the flood starter, db_lock.py, the helper's two flags, the third scrape target, and the per-Worker panel in the sections where their neighbors live, add the exercise 06 facts from the captures under "Exercise facts", and update the root marker and test counts if they changed. Keep it free of anything the code already says plainly.
   - docs/drafts/README.md: list seven parts, the primer, smell-reports.md, and the provenance draft; update the sentence near line 28 about open CLAUDE_HELP questions.
   - Run content-design:review-content over the six exercise READMEs and the seven drafts as one final pass, and fix what it finds without changing any quoted capture.

4. Verify:
   - just check && just check-practice exits 0; just lint-keyboard (default file set) and just lint-keyboard docs/drafts/event-loop-primer.md exit 0; just lint-prose shows no error; grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution returns nothing; grep -n "three layers" README.md returns nothing.

5. Document:
   - none beyond the three files.
```

## Section 10: Review Handoff

**Tools:**
- Skills: none
- MCPs: none
- Linters: just lint-keyboard .ai-sessions/review-decisions-fleet-localization.md

### Step 15: Decisions Record And The Pull Request Comment (task)

**NOTE**: The owner chose to review once, after the build, and asked for one pull request comment that lists each decision the builder made so any of them can be overruled.
The record is a committed file so the comment's text is linted and privacy-checked before it is posted.
Every item is worded as a build decision; none is called a ruling.

```text
1. Scope:
   - Artifact(s): .ai-sessions/review-decisions-fleet-localization.md, one comment on pull request 4.
   - Desired end state: the owner has one linear reading order for the review and one list of decisions to accept or overrule.

2. Tooling:
   - Skills: none
   - MCPs: none
   - External: gh, just lint-keyboard, just lint-prose

3. Do the work:
   - Write .ai-sessions/review-decisions-fleet-localization.md with three parts: a reading order for the review (the primer, the root README, exercises 01 to 06 in order, then the drafts), the eleven build decisions on the older open questions (the list under Implementation Guidelines, each with one line on what was done and where), and the decisions marked "confirm at review" in spec.md plus the exercise 06 design decisions from this plan's Architecture Recap. Add any CLAUDE_HELP tag left in the tree with its file and line.
   - Keep each item to two lines or fewer, one sentence per line, with the file to look at.
   - Run just lint-keyboard and just lint-prose on the file and fix what they find.
   - Privacy check, as its own command: confirm the file names no customer, company, namespace, ticket, internal system, course, or hostname.
   - Post it with gh pr comment 4 --body-file .ai-sessions/review-decisions-fleet-localization.md.

4. Verify:
   - gh pr view 4 --comments shows the comment; just check && just check-practice exits 0; git status is clean after the commit.

5. Document:
   - none beyond the record itself.
```

## Implementation Guidelines

- One mechanism only: a blocking call on the Worker's shared asyncio event loop.
  No step adds a slot-sizing, heartbeat-tuning, timeout-tuning, or retry-policy lesson, and exercise 06's flood is a teaching fixture, not a load test.
- The failure is visible in the execution without a dashboard: the starter's summary and the Event Histories show it, and Grafana only corroborates.
- Follow python:python: full type hints, Google-style docstrings on public interfaces, no single-letter names, PEP 604 unions, and absolute flat top-level imports inside exercise copies.
- The root package is frozen.
  New code lands under `exercises/`, `scripts/`, `tests/`, or `observability/`, inside the `paths:` list in `spec.md`.
- No new Python runtime dependency: the standard library plus `httpx` and `temporalio`, which are already present; `py-spy` stays an on-demand `uvx` tool.
- The dev server single binary only (`just server`, which passes `--metrics-port 9465`); the compose stack holds Prometheus and Grafana only, on docker-compose v1; never attempt sudo.
- Practice and solution layout with the marker carve-out: every deliberate bug carries the exact marker, and `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing.
- Every quoted block of output is a capture of that copy; flag a missing capture with `<CLAUDE_HELP>` tags and never fill the gap.
  State a figure with the run or runs it came from, and never present one run as general.
- Each capture flood runs on a freshly started dev server.
  If a receipt fails or stalls after the fix, stop and correct `spec.md` before any README is written.
- Tests never need a running server except through the SDK's test facilities, and all network calls are mocked.
- The gate: the root run excludes `exercises/`; `just check` loops over every `exercises/*/solution` with ruff, ruff format, mypy, and pytest; `just check-practice` loops over every practice copy with ruff and mypy only; the observability config tests and the helper tests run in the root pytest.
- No name labels a role (no "victim" in an identifier or a file name), and the `default` recipe stays first in the justfile.
- Demo behavior is deterministic: the one gate is the server-side STARTED check, and nothing races.
- Privacy: the repository is public.
  No committed file names a customer, a company, a namespace, a ticket, an internal system, a course, or the capture machine's hostname; identities in committed excerpts and fixtures read `PID@host`.
- Writing rules for every committed file: no em or en dashes, no banned vocabulary from the owner's list, straight quotes, one sentence per line, sentence case headings in exercise READMEs and drafts, Title Case elsewhere.
- Prose steps run content-design:tutorial-writing, then voice:teaching, then the draft, then content-design:review-content, after `just preflight` exits 0.
  Each new artifact (the exercise 06 README and part 7) gets a section in `docs/drafts/smell-reports.md`; the owner is not asked to read it and reviews by pull request comments.
- Vale scope: `MasonBase` on every Markdown file, `MasonTechnical` under `docs/drafts/` and `exercises/`; `docs/drafts/tutorial-original-draft.md` is provenance and is never linted.
- Never present `maximum_attempts=1` as exactly-once execution, and check Temporal claims against the temporal-docs MCP.
- Build decisions on the eleven older open questions (apply them where the steps say, and list them in Step 15):
  1. The failures panel stays as it is, and exercise 02 keeps saying the panel misses a Heartbeat timeout.
  2. Exercise 02's solution panel images are recaptured with a window that starts at the fleet start (Step 8).
  3. Exercise 05's near-empty Workflow Task panels stay, with one sentence saying why (Step 11).
  4. The primer stays unnumbered.
  5. The primer's third diagram stays, with its claim checked against the temporal-docs MCP.
  6. Part 1 quotes the read-only `sysctl kernel.yama.ptrace_scope` output, the sudo write stays a command with no output, and `temporal task-queue describe` stays the reliable backlog reading (Steps 8 and 13).
  7. Part 5's forced-timeout demo stays a described extension.
  8. The root README's list of permitted edits to captured output gains ANSI stripping (Step 14).
  9. The latency panel is read again during a fresh root `just block` run, and the 29-second figure is corrected if it differs (Steps 8 and 14).
  10. Part 1's clone command switches to HTTPS (Step 13).
  11. The layer count is four, and `README.md` line 22 is fixed (Step 14).
- The full local gate is `just check` plus `just check-practice`; pytest alone (root, which excludes `exercises/`) is the autonomous-run verification command.
- Never commit to main; work on the `scaffold` branch (pull request 4).
  Only the owner merges to main.
  No attribution trailers in commits or pull requests, and never `--no-verify`.

## Success Metrics

- `just check` and `just check-practice` are green with exercise 06 in both loops.
- `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing, and the same search over `exercises/06-finding-the-frozen-worker/practice` returns one line.
- On two Workers, the healthy flood of the practice copy fails no receipt, and the bad flood shows failed receipts and the timeline in its summary.
- `just receipt-gaps --by-identity --summary` puts the Workflow Task timeouts of the bad flood on one identity, and the helper's default output is unchanged byte for byte.
- After the fix, the bad flood on two Workers fails no receipt in the capture the README quotes.
- Prometheus lists three targets, and the dashboard's per-Worker panel draws one line per Worker.
- The recognition block is in the root README and the primer, and Part B of every exercise README links to it.
- Exercise 03's second-Worker step is in the main path with `--bad 2` and `--bad 4`.
- The teaching-code note is in the root README, and the single-Worker sentence is in exercises 01 to 05 and parts 1 to 6.
- Six exercise READMEs and seven drafts pass `just lint-keyboard`, show no Vale error, and have been through `/review-content`.
- `just preflight` exits 0.
- One comment on pull request 4 lists every build decision for the owner.
- The arc ships as commits on the `scaffold` branch against main, with a session summary per commit.
