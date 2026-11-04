# Exercise 5: Catching a short blocking call before it ships

During this exercise, you will

- Run a fleet where every Workflow completes and nothing times out
- Compare the first Workflow Task of a receipt with and without a short blocking call on the Worker
- Turn on asyncio debug mode and read its slow-callback warning
- Use `py-spy dump` to name the line behind the warning
- Write a test that probes every `async def` Activity, then move the blocking call to a thread

Make your changes to the code in the `practice` subdirectory.
Look for the `TODO PART C` and `TODO PART D` comments, which mark where you make changes.
If you need a hint or want to verify your changes, look at the complete version in the `solution` subdirectory.

## Prerequisites

Finish the setup in the root [README](../../README.md#quickstart) first.
You need the `temporal` command, `uv`, and Python 3.14 or newer.
You also use `py-spy`, which the repository does not install.
You run it on demand with `uvx py-spy dump --pid <PID>`.

Part E compares a Grafana panel before and after the fix.
Start the dashboard stack once, from the repository root.

```sh
just metrics
```

Grafana serves the provisioned **Async Debug** dashboard at http://localhost:3000.
Start the dev server with `just server` so that Prometheus can read it on port 9465.
The Worker exports its own metrics on port 9464.

The practice copy here calls the public providers with the async `httpx.AsyncClient`, unlike Exercise 1.
The HTTP calls do not block.
The call that does block takes about a third of a second.

## Part A: Run the Workflow

The earlier exercises froze a Worker for half a minute, and the failures were loud.
This one is quiet.
Nothing times out and nothing fails.
Every run completes, and the receipts take a little longer than they should.
A delay this short does not show up as a failure.

The `get_location` Activity archives an audit trail for each lookup before it asks a provider for the location.
The archiving compresses a block of bytes.
The same Worker also runs an `OrderReceiptWorkflow`, which does nothing slow.

Do not read the Activity code yet.
Part B asks you to find the cause with tools.

1. Change to the `exercises/05-catching-blockers-early/practice` directory.
2. Start the Worker.

   ```sh
   uv run python worker.py
   ```

   The Worker prints a banner with its PID.
   Keep this terminal open and note the PID.

3. Open another terminal in the same directory and submit a fleet of receipts alone, for a reference reading.

   ```sh
   uv run python starter.py --geo 0 --receipts 3 --rollups 0
   ```

4. Submit the practice fleet, with geo runs beside the receipts.

   ```sh
   uv run python starter.py --geo 3 --receipts 3 --rollups 0
   ```

Here is what the starter printed for the practice fleet in the capture for this exercise.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt receipt-43ea837a-8d74-4f32-9594-6be2ddf15528: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-5f6cbd4a-ccd0-4eca-aab8-0946c6faa313: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
receipt receipt-13b2c3b7-eaf3-4b35-8541-6c1b2f840a85: OrderReceiptOutput(receipt='order order-2: 59.97 USD')
geo geo-cc81da64-304b-4899-8ab1-7b957cf80844: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (22000 audit records)')
geo geo-e4273f38-8968-4445-8634-0731ab8a420a: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (22000 audit records)')
geo geo-3bb56178-1e2f-4234-ad34-8098b6e75b04: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (22000 audit records)')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Every Workflow completed.
To see what changed, read the first Workflow Task of a receipt in each fleet.
Run `temporal workflow show -w <receipt workflow ID> --output json`.
Find the first `WORKFLOW_TASK_STARTED` event and the first `WORKFLOW_TASK_COMPLETED` event, and subtract their `eventTime` values.

The capture below holds those numbers for the receipts-only fleet and for the practice fleet.
The author helper script computed them from each Event History, and the script is not in the repository.
The `WT1 started->completed` field is the first Workflow Task.

<CLAUDE_HELP>
The capture has no `workflow show` output for this exercise, only the helper script output.
A reader has to do the subtraction by hand from the JSON.
Commit a small script, or add a captured JSON excerpt?
</CLAUDE_HELP>

This is the receipts-only fleet.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt-ee390ee6 total 124ms | WT1 started->completed 19ms | validate_order: sched->started 4ms started->completed 17ms | compute_total: sched->started 4ms started->completed 4ms | format_receipt: sched->started 4ms started->completed 10ms
receipt-53011e69 total 109ms | WT1 started->completed 20ms | validate_order: sched->started 7ms started->completed 10ms | compute_total: sched->started 3ms started->completed 7ms | format_receipt: sched->started 5ms started->completed 4ms
receipt-5ae07bf1 total 117ms | WT1 started->completed 23ms | validate_order: sched->started 3ms started->completed 10ms | compute_total: sched->started 9ms started->completed 6ms | format_receipt: sched->started 3ms started->completed 9ms
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

This block keeps only the three receipt lines of the first practice fleet, the same fleet as the starter output earlier.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt-43ea837a total 481ms | WT1 started->completed 330ms | validate_order: sched->started 58ms started->completed 7ms | compute_total: sched->started 15ms started->completed 7ms | format_receipt: sched->started 6ms started->completed 8ms
receipt-5f6cbd4a total 459ms | WT1 started->completed 320ms | validate_order: sched->started 44ms started->completed 8ms | compute_total: sched->started 13ms started->completed 7ms | format_receipt: sched->started 10ms started->completed 6ms
receipt-13b2c3b7 total 442ms | WT1 started->completed 313ms | validate_order: sched->started 31ms started->completed 7ms | compute_total: sched->started 4ms started->completed 7ms | format_receipt: sched->started 13ms started->completed 6ms
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Without geo runs, the first Workflow Task of a receipt takes 19 to 23 milliseconds.
With them, it takes 298 to 394 milliseconds across the three runs in the capture.
The Activities in the receipt still finish in milliseconds, with one 375-millisecond `validate_order` as the exception.
The slow part is the Workflow Task, before the Activities start.
The receipt code is the same in both fleets, so something on the Worker holds up the Workflow Task.

## Part B: Diagnose the delay

The delay is short, so you cannot catch it with `asyncio ps` by luck, and nothing fails to point you at it.
Two tools help here.
Asyncio debug mode reports slow callbacks, and `py-spy` names the line once you know when to look.
Replace `<PID>` with the PID from the Worker banner.

### Step 1: Turn on asyncio debug mode

Python has a debug mode for asyncio.
In that mode, the event loop logs a warning for every callback that runs longer than 0.1 seconds.
The [asyncio development guide](https://docs.python.org/3/library/asyncio-dev.html#debug-mode) describes it.

Stop the Worker with `CTRL+C` and start it again with the debug mode on.

```sh
PYTHONASYNCIODEBUG=1 uv run python worker.py
```

Submit the practice fleet again.

```sh
uv run python starter.py --geo 3 --receipts 3 --rollups 0
```

Debug mode prints a warning for each slow step.
The capture holds six warnings for two practice fleets.
This block keeps only the first warning.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Executing <Task pending name='Task-37' coro=<_ActivityWorker._handle_start_activity_task() running at /home/ziggy/temporal-async-debug/.venv/lib/python3.14/site-packages/temporalio/worker/_activity.py:351> created at /home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/lib/python3.14/asyncio/tasks.py:395> took 0.367 seconds
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Read the warning from the left.
It names a task, `_ActivityWorker._handle_start_activity_task`, running at `_activity.py:351` in the SDK.
It ends with `took 0.367 seconds`.
The six warnings in the capture ran from 0.355 to 0.384 seconds.

The warning tells you that an Activity ran on the loop for more than a third of a second.
That matches the 298 to 394 millisecond gap you measured.
The warning does not name your code.
The SDK handler is the frame that calls your Activity, so the line that blocks is further down.

### Step 2: Name the line with py-spy

`py-spy dump` reads the operating system thread stack, so it can name the line.
The blocking call lasts about 350 milliseconds, so a single dump often misses it.
Run the dump several times while the fleet runs.

```sh
uvx py-spy dump --pid <PID>
```

The capture needed 12 tries before the main thread was inside the blocking call.
This block keeps only the `MainThread` stack from the capture.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Process 2682858: /home/ziggy/temporal-async-debug/.venv/bin/python worker.py
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 2682858 (active): "MainThread"
    _archive_audit_trail (activities.py:142)
    get_location (activities.py:188)
    _ActivityInboundImpl.execute_activity (temporalio/worker/_activity.py:889)
    _ActivityWorker._execute_activity (temporalio/worker/_activity.py:681)
    _ActivityWorker._handle_start_activity_task (temporalio/worker/_activity.py:351)
    Handle._run (asyncio/events.py:94)
    BaseEventLoop._run_once (asyncio/base_events.py:2038)
    BaseEventLoop.run_forever (asyncio/base_events.py:677)
    BaseEventLoop.run_until_complete (asyncio/base_events.py:706)
    Runner.run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (worker.py:122)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The top frame is `_archive_audit_trail` at `activities.py:142`, called by `get_location` at `activities.py:188`.
The state is `active`, and the thread is the `MainThread`, which runs the event loop.
Line 142 is the `zlib.compress` call.
The loop holds one call for about 350 milliseconds each time a geo run starts.

### Step 3: Check the dashboard

Open the dashboard at http://localhost:3000 and find the panel named **Workflow Task Execution Latency**.
This panel is the fleet-wide view of what the tooling found.
Here the view is weak.

![The Workflow Task Execution Latency panel during the practice fleets, with the receipt and geo lines between about 20 and 190 milliseconds.](../../docs/images/05-practice-stall-workflow-task-latency.png)

The lines sit between 20 and 190 milliseconds, with most readings near 100.
That is a small number on a chart.
Nothing on the panel would alarm anyone, which is the point of this exercise.
The debug-mode warning and the thread dump found what the panel could not.

## Part C: Find the bug

Open `activities.py` in the `practice` directory and find the two `TODO PART C` comments.

1. Find `_archive_audit_trail`.
   The function takes a block of bytes and calls `zlib.compress` on it.
   Most of its time goes to that one call.
2. Find `get_location`.
   The function is an `async def` Activity, and it calls `_archive_audit_trail` directly, with no `await`.
3. Find the comment that starts with `ANTIPATTERN (deliberate, for teaching)`.
   It sits on the line before the call that `py-spy` named.

A plain call inside an `async def` Activity runs on the event loop and holds it until the call returns.
This one returns in a third of a second, so nothing times out.
Every other task on the Worker waits it out anyway.

The fix is to run the call off the loop.
The work is short and has a clear end, and `zlib.compress` releases the GIL while it works.
A thread runs it, and the event loop keeps running beside it.

Exercise 4 showed what goes wrong when you do this with long work that a timeout must stop.
Nothing stops a thread that `asyncio.to_thread` already started.
Here the work lasts a third of a second and has no Heartbeat timeout, so waiting on a thread is safe.

## Part D: Write a test, then fix the bug

The delay is invisible in production.
A test can catch it before it ships.
You write one test that probes every `async def` Activity the Worker registers, so the next blocking call fails the build.

1. From the `practice` directory, run the tests.

   ```sh
   uv run python -m pytest -o pythonpath="$PWD" tests
   ```

   One test fails on purpose.
   The stub carries a `TODO PART D` comment.
2. Open `tests/test_probe_all_activities.py` and read the comment in `test_async_activities_do_not_starve_the_event_loop`.
   It describes the test you write.
   You take `worker.ACTIVITIES`, so the test can parametrize at collection time, and keep the `async def` entries.
   You run each one beside a coroutine that records a timestamp every 50 milliseconds, with the network mocked.
   You size the payload of `get_location` so that archiving it on the loop takes well over 0.2 seconds.
   The test asserts that no gap between ticks reaches 0.2 seconds, for every Activity.
3. Write the test.
   If you need a hint, the finished version is in `solution/tests/test_probe_all_activities.py`.
4. Run the tests again.
   Your test fails for `get_location`, because the archiving holds the loop.
5. Open `activities.py`.
   Add the import that moving the work off the loop needs, at the `TODO PART C` comment near the top.
   Replace the direct call in `get_location` with `await asyncio.to_thread(...)`, passing `_archive_audit_trail` and its two arguments.
   Delete the `ANTIPATTERN` comment and the `TODO PART C` comments.
6. Run the tests a third time.
   They all pass.

The test is the lasting part of this exercise.
It probes every Activity that the Worker registers, so a new `async def` Activity gets the same check without any edit.

## Part E: Redeploy and verify

Stop the old Worker with `CTRL+C`, then start it again with debug mode on, from the `practice` directory.

```sh
PYTHONASYNCIODEBUG=1 uv run python worker.py
```

Submit the same fleet from your second terminal.

```sh
uv run python starter.py --geo 3 --receipts 3 --rollups 0
```

This is what the starter printed in the capture of the solution copy.
Every Workflow completes, as before.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt receipt-228b2574-1728-4e81-97e4-861517889fb3: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-cb117a78-d48a-4c8e-bcdd-8a6be6faab19: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
receipt receipt-b6e5a47d-6413-491f-9858-5279c494c933: OrderReceiptOutput(receipt='order order-2: 59.97 USD')
geo geo-074ea430-de27-491a-9e10-83060754a99d: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (22000 audit records)')
geo geo-177c77b1-8c32-4f3b-a3d0-35ad3a5c2fc2: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (22000 audit records)')
geo geo-994e0437-1911-420b-b20d-53c5491976dc: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (22000 audit records)')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Now read the first Workflow Task of the receipts.
This block keeps only the three receipt lines of the first solution fleet, from the same helper script as in Part A.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt-cb117a78 total 419ms | WT1 started->completed 37ms | validate_order: sched->started 10ms started->completed 27ms | compute_total: sched->started 32ms started->completed 14ms | format_receipt: sched->started 50ms started->completed 50ms
receipt-b6e5a47d total 322ms | WT1 started->completed 31ms | validate_order: sched->started 67ms started->completed 18ms | compute_total: sched->started 15ms started->completed 7ms | format_receipt: sched->started 12ms started->completed 7ms
receipt-228b2574 total 301ms | WT1 started->completed 61ms | validate_order: sched->started 7ms started->completed 12ms | compute_total: sched->started 68ms started->completed 15ms | format_receipt: sched->started 13ms started->completed 19ms
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The first Workflow Task takes 37, 31, and 61 milliseconds here.
Across the three solution fleets in the capture, all nine receipts read between 12 and 61 milliseconds.
In the practice fleets, they read between 298 and 394.
The loop stays free while the Worker archives the audit trail.

The debug-mode log is the other check.
This block keeps only the first nine lines of the Worker log from the solution capture, with debug mode on, during two fleets.
The banner comes first, and the shutdown traceback follows it.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
========================================================================
temporal-async-debug worker running with PID 2690262
Inspect the live event loop from another terminal with either of:
    python -m asyncio ps 2690262
    python -m asyncio pstree 2690262
Prometheus metrics: http://127.0.0.1:9464/metrics
========================================================================
Traceback (most recent call last):
  File "/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/lib/python3.14/asyncio/runners.py", line 127, in run
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

No slow-callback warning appears between the banner and the shutdown.
The same fleet produced six warnings on the practice copy.

Last, look at the **Workflow Task Execution Latency** panel again.

![The Workflow Task Execution Latency panel after the fix, with the receipt and geo lines between 6 and 18 milliseconds.](../../docs/images/05-solution-live-workflow-task-latency.png)

The lines now sit between 6 and 18 milliseconds, and the practice panel showed about 100.
The panel is a weak signal in both states, and it moves in the right direction.

## Conclusion

You found a blocking call that no timeout would ever report.
Debug mode flagged a slow callback, `py-spy` named the line, and `asyncio.to_thread` moved the work off the loop.
The test you wrote probes every `async def` Activity on the Worker, so the next blocker fails the build and never reaches production.

### This is the end of the exercise.
