# Moving CPU-bound work off the event loop
<!-- TODO: venue not yet chosen. -->

### Introduction

A blocking call is not always a call that waits.
A calculation inside an `async def` Activity also holds the event loop, and it holds the Global Interpreter Lock (GIL) too.
From a Workflow's point of view, both look the same.
A CPU reading tells them apart.

In this tutorial, you run a fleet where one Activity does a long calculation and the other Workflows stall.
You use `python -m asyncio ps` and `py-spy dump` to find the calculation, and you read the CPU of the Worker to compare it with the frozen loop from part 2.
Then you write a test that fails while the calculation holds the loop and move the calculation to a thread.
You also see what that change does and does not buy.

This is part 4 of the series "Debugging blocking calls in Temporal async Activities".
Previous: TODO (link to part 3, "Fixing a sleep between heartbeats in an async Activity").
Next: TODO (link to part 5, "Stopping a thread that outlives its Activity attempt").

## Prerequisites

To complete this tutorial, you need:

- The setup from part 1 and the process inspection setting it describes.
- The server from `just server` and the dashboard stack from `just metrics`, both running.
- The `exercises/03-cpu-bound` directory of the demo repository, which holds a `practice` copy with the bug and a `solution` copy with the fix.
- `py-spy`, which you run on demand with `uvx py-spy dump --pid <PID>`.

The practice copy calls the public providers with the async `httpx.AsyncClient`, so the HTTP call does not block.
The calculation that follows it does.

## Step 1: Running the fleet

The `get_location` Activity asks a public provider for the location and then tags the result with a short digest.
The digest comes from hashing the location text again and again in a loop.
Most lookups use a small number of rounds, and the tag takes a moment.
One run in the fleet asks for a far larger number of rounds.
The same Worker also runs a `SalesRollupWorkflow` and an `OrderReceiptWorkflow`, and neither one hashes anything.
Do not read the Activity code yet.

Change to the practice directory and start the Worker:

```sh
cd exercises/03-cpu-bound/practice
uv run python worker.py
```

Note the PID in the banner.
In a second terminal, change to the same directory and submit the fleet:

```sh
uv run python starter.py --bad 1 --geo 1 --rollups 1 --receipts 2
```

The `--bad 1` option gives one geo run the large hashing job.
The job takes about 25 to 30 seconds on the machine that made the capture.
The time scales with the speed of your CPU, so yours can differ.
This is the output from the capture of this exercise:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
rollup rollup-a318bbd3-dd9e-424b-9d12-4ed37772c0d2 FAILED: Activity task timed out
geo geo-1073bc5c-7691-420c-a02d-bb2935006248: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (80bb60a0)')
receipt receipt-badf2910-5ee2-4b0f-a118-ac2433029c1d: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-aad5961f-e57e-4096-93c7-aab6789bc56f: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
geo geo-66bccc79-42f1-4c89-8040-50b1d269399f: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (0a547457)')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The rollup failed with `Activity task timed out`, and the receipts completed.
You read the Event History of one receipt next.

## Step 2: Reading the Event History

Run `temporal workflow show -w <receipt workflow ID>` for one receipt.
This capture keeps the first ten lines, which cover the first Workflow Task and the first Activity.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Progress:
  ID           Time                     Type           
    1  2026-11-03T23:36:52Z  WorkflowExecutionStarted  
    2  2026-11-03T23:36:52Z  WorkflowTaskScheduled     
    3  2026-11-03T23:36:52Z  WorkflowTaskStarted       
    4  2026-11-03T23:37:02Z  WorkflowTaskTimedOut      
    5  2026-11-03T23:37:12Z  WorkflowTaskScheduled     
    6  2026-11-03T23:37:12Z  WorkflowTaskStarted       
    7  2026-11-03T23:37:21Z  WorkflowTaskCompleted     
    8  2026-11-03T23:37:21Z  ActivityTaskScheduled     
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The first Workflow Task started at 23:36:52.
At 23:37:02 the history shows `WorkflowTaskTimedOut`, because the Worker never replied to that task.
The second Workflow Task started at 23:37:12 and completed at 23:37:21.
The receipt waited about 29 seconds for its first decision, across two Workflow Tasks.
A receipt does no hashing and no I/O, so the stall needs an explanation.

The rollup says the same thing.
Run `temporal workflow show -w <rollup workflow ID>`.
This capture starts at the `Results:` line and runs to the end.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Results:
  Status   FAILED
  Failure  
    Message: Activity task timed out
    Cause:
        Message: activity ScheduleToClose timeout
        Cause:
            Message: activity StartToClose timeout
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The first steps of the diagnosis match part 2, and one extra reading separates the two causes.
Run the next three steps about 10 seconds after you submit the fleet.
Replace `<PID>` with the PID from the Worker banner.

## Step 3: Finding the stuck task and the blocking line

`python -m asyncio ps` reads the memory of the Worker from outside the process, so it answers during a freeze.
Run it from the repository root:

```sh
uv run python -m asyncio ps <PID>
```

The output lists the tasks on the loop:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
tid        task id              task name            coroutine stack                                    awaiter chain                                      awaiter name    awaiter id     
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
2622375    0x7d1bac31b2f0       Task-1               Worker._run -> Worker.run -> main                                                                                     0x0            
2622375    0x7d1bac31be30       Task-2               Event.wait -> Worker._run.<locals>.raise_on_shutdown _wait -> wait                                      Task-5          0x7d1bac45fa10 
2622375    0x7d1bac34f140       Task-3               _wait -> wait -> _ActivityWorker.run               _wait -> wait                                      Task-5          0x7d1bac45fa10 
2622375    0x7d1bac34ebd0       Task-4               Worker.poll_workflow_activation -> _WorkflowWorker.run _wait -> wait                                      Task-5          0x7d1bac45fa10 
2622375    0x7d1bac45fa10       Task-5               _wait -> wait                                      Worker._run -> Worker.run -> main                  Task-1          0x7d1bac31b2f0 
2622375    0x7d1bac45d550       Task-6               Queue.get -> _ActivityWorker.run.<locals>.raise_from_exception_queue _wait -> wait -> _ActivityWorker.run               Task-3          0x7d1bac34f140 
2622375    0x7d1baa994050       Task-20              sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task                                                                    0x0            
2622375    0x7d1bac1674d0       Task-43              _ActivityWorker._handle_start_activity_task                                                                           0x0            
2622375    0x7d1bac1672f0       Task-44              Worker.poll_activity_task                          _wait -> wait -> _ActivityWorker.run               Task-3          0x7d1bac34f140 
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Task-43 holds only `_ActivityWorker._handle_start_activity_task`, the outermost call, with no call inside it.
Task-20, the rollup, has `sleep` as its innermost call.
The shape matches a frozen loop, but the tool cannot name the line.
Run `py-spy dump` for that:

```sh
uvx py-spy dump --pid <PID>
```

This capture keeps only the `MainThread` stack.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Process 2622375: /home/ziggy/temporal-async-debug/.venv/bin/python worker.py
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 2622375 (active+gil): "MainThread"
    _stretch_digest (activities.py:119)
    get_location (activities.py:178)
    _ActivityInboundImpl.execute_activity (temporalio/worker/_activity.py:889)
    _ActivityWorker._execute_activity (temporalio/worker/_activity.py:681)
    _ActivityWorker._handle_start_activity_task (temporalio/worker/_activity.py:351)
    Handle._run (asyncio/events.py:94)
    BaseEventLoop._run_once (asyncio/base_events.py:2046)
    BaseEventLoop.run_forever (asyncio/base_events.py:677)
    BaseEventLoop.run_until_complete (asyncio/base_events.py:706)
    Runner.run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (worker.py:115)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The top frame, the innermost call, is `_stretch_digest` at `activities.py:119`, called by `get_location` at `activities.py:178`.
The main thread runs the event loop, so the hashing holds the loop.
Look at the state in the first line of the thread.
It says `active+gil`, where a waiting thread says `idle`.
The thread runs, and it holds the GIL.

## Step 4: Reading the CPU

This reading separates this exercise from part 2.
Run `top` for the Worker PID, once when the Worker is idle and once during the freeze:

```sh
top -b -d 1 -n 2 -p <PID> | tail -8
```

The `-n 2` option prints two frames, so the second frame reports CPU use over a real one-second interval.
Each capture below keeps only the column header and the process row.
This is the idle reading.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2622375 ziggy     20   0  572496  65856  27116 S   0.0   0.4   0:00.55 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

This is the reading about 10 seconds into the run.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2622375 ziggy     20   0  727024  78360  31680 R  99.0   0.5   0:08.13 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The state column changed from `S` to `R`, and the CPU went from 0.0 to 99.0 percent.
In part 2, the frozen loop read 0.0 percent, because the Worker waited on a socket.
Here the Worker computes.
Both freezes look the same in `asyncio ps`, and the CPU number tells them apart.

The reading of 99.0 percent also tells you that the process uses one core.
The loop thread holds the GIL, so adding threads inside this process cannot add CPU.

## Step 5: Checking the dashboard

Open http://localhost:3000 and find the **Workflow Task Execution Latency** panel.
It shows the fleet-wide view of what the tools showed you.

![The Workflow Task Execution Latency panel during the freeze, with the rollup line near 5.4 seconds and the geo line near zero.](../images/03-practice-frozen-workflow-task-latency.png)

The rollup line jumps to about 5.4 seconds while the geo line stays near zero.
The panel averages over 30 seconds, so a 29-second stall reads as about 5 seconds.
Read the true length from `temporal workflow show`, as you did in Step 2.

## Step 6: Finding the cause in the code

Open the file `exercises/03-cpu-bound/practice/activities.py` in your editor.
Find `_stretch_digest` first.
It feeds a digest back into `hashlib.sha256` once per round, and its length depends on `rounds`:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
<!-- fmt:off -->
```python
    digest = hashlib.sha256(seed.encode()).digest()
    for _ in range(rounds):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()
```
<!-- fmt:on -->
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

This loop is the CPU-bound work.
It never reaches an await, so it holds the loop and the GIL for as long as it runs.
Now find the call in `get_location`, which is an `async def` Activity.
The comment before the call starts with `ANTIPATTERN (deliberate, for teaching)`, and the call is the line that `py-spy` named.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
<!-- fmt:off -->
```python
            # ANTIPATTERN (deliberate, for teaching): hashing in a plain call holds the GIL on the one event loop
            # for every round, so everything else on the worker waits. Correct: a def Activity on the worker's
            # activity_executor, and more Worker processes when you need more CPU. Do not copy.
            tag = _stretch_digest(location, work_rounds)[:8]
            return f"{location} ({tag})"
```
<!-- fmt:on -->
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The same fix as in part 2 applies.
A plain `def` Activity runs on the `activity_executor` of the Worker, a pool of threads, so the loop thread stays free.
Because the Activity becomes a `def`, the HTTP client inside it has to change too.
A plain function cannot use `await`, so the second `TODO PART C` comment points at the client.
You switch from the async `httpx.AsyncClient` to the sync `httpx.Client`.

## Step 7: Writing a test that probes the event loop

You write the test before you change the code.
From the `practice` directory, run the tests:

```sh
uv run python -m pytest -o pythonpath="$PWD" tests
```

One test fails on purpose, and its stub carries a `TODO PART D` comment.
Open `tests/test_probe.py` and read the comment in `test_get_location_does_not_starve_the_event_loop`.
You pick a work size that hashes for about a second on your machine.
You run `get_location` the way the Worker does, beside a small coroutine that records a timestamp every 50 milliseconds.
The test asserts that no gap between ticks reaches 0.2 seconds.

If you need a hint, the finished version is in `solution/tests/test_probe.py`.
Run against the practice copy, a test written like it fails first because the Worker has no `activity_executor`.
A probe that runs the `async def` directly fails because a gap between ticks reaches the length of the hashing.
Run the tests again after you write yours.

## Step 8: Moving the calculation to a thread

Open `activities.py` in the `practice` directory.
Remove the `async` keyword from `get_location`.
Change the `async with httpx.AsyncClient(...)` line to `with httpx.Client(...)`, and remove the `await` before `client.get`.
Delete the `ANTIPATTERN` comment and the `TODO PART C` comments.
The solution shows the new signature and the sync client.
The signature comes first:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
<!-- fmt:off -->
```python
@activity.defn
def get_location(ip: str, work_rounds: int) -> str:
```
<!-- fmt:on -->
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `def` keyword replaces `async def`, so the Worker runs the Activity on its `activity_executor`.
The client in that function is now the sync `httpx.Client`:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
<!-- fmt:off -->
```python
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url_template, parse in _rotated(GEO_PROVIDERS):
            url = url_template.format(ip=ip)
            try:
                response = client.get(url)
                response.raise_for_status()
```
<!-- fmt:on -->
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The client call no longer awaits, so the whole function is plain synchronous code.

Next, open `worker.py` and find the `TODO PART D` comment in `build_worker`.
Pass the Worker an `activity_executor` that is a `ThreadPoolExecutor` with `max_workers` equal to `MAX_CONCURRENT_ACTIVITIES`.
Add the import at the top of the file.
The solution has these lines:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
<!-- fmt:off -->
```python
        activity_executor=ThreadPoolExecutor(max_workers=MAX_CONCURRENT_ACTIVITIES),
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
```
<!-- fmt:on -->
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Run the tests a third time.
They all pass.

## Step 9: Verifying the fix

Stop the old Worker with `CTRL+C`, and start it again from the `practice` directory:

```sh
uv run python worker.py
```

Submit the same fleet from your second terminal:

```sh
uv run python starter.py --bad 1 --geo 1 --rollups 1 --receipts 2
```

This is what the starter printed in the capture of the solution copy.
Every Workflow completes, including the rollup.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
rollup rollup-19d1e4e0-0586-4e89-bf67-6250a044f00d: SalesRollupOutput(summary='Sales rollup for 2026-01: total 6030')
geo geo-2c45a01b-eb0c-48fa-aa32-50c3737f09d0: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (80bb60a0)')
receipt receipt-a95a7bcd-eb87-4a25-a704-8670153f629f: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-d79f1c1a-58a6-40e9-9851-6d6b280b06f3: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
geo geo-6f151c04-4113-47fb-83be-842fed0df268: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy (0a547457)')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Run `py-spy dump` again during the job:

```sh
uvx py-spy dump --pid <PID>
```

This capture keeps only the `MainThread` stack.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Process 2628463: /home/ziggy/temporal-async-debug/.venv/bin/python worker.py
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 2628463 (idle): "MainThread"
    EpollSelector.select (selectors.py:452)
    BaseEventLoop._run_once (asyncio/base_events.py:2008)
    BaseEventLoop.run_forever (asyncio/base_events.py:677)
    BaseEventLoop.run_until_complete (asyncio/base_events.py:706)
    Runner.run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (worker.py:117)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The main thread sits in `EpollSelector.select`, which is a healthy loop waiting for work.
This capture keeps only the stack of the thread that does the hashing.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Thread 2629021 (active+gil): "ThreadPoolExecutor-0_0"
    _stretch_digest (activities.py:120)
    get_location (activities.py:173)
    _execute_sync_activity (temporalio/worker/_activity.py:951)
    WorkerContext.run (concurrent/futures/thread.py:73)
    _WorkItem.run (concurrent/futures/thread.py:86)
    _worker (concurrent/futures/thread.py:119)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The hashing now runs on `ThreadPoolExecutor-0_0`, and its state is `active+gil`.
Run `top` again.
This capture keeps only the column header and the process row.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2628463 ziggy     20   0 1002020  79060  31620 S  99.0   0.5   0:08.13 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The CPU still reads 99.0 percent.
Moving the work to a thread did not make it cheaper.
The pool thread still holds the GIL while it hashes.
The difference is that the event loop gets its turns, so the Worker keeps serving everything else.

The receipts show what that means.
The repository ships a helper that reads each receipt's Event History and prints the Workflow Task time and the Activity waits.
Run it from the repository root with the receipt Workflow IDs from your run:

```sh
just receipt-gaps <receipt workflow ID> <receipt workflow ID>
```

This block comes from an earlier script with the same output format, run on the two receipts in the solution capture.
The capture predates the commit of `scripts/receipt_gaps.py`, so `just receipt-gaps` did not print it.
The helper you run prints the same columns.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt-a95a7bcd total 3559ms | WT1 started->completed 79ms | validate_order: sched->started 3194ms started->completed 21ms | compute_total: sched->started 4ms started->completed 23ms | format_receipt: sched->started 5ms started->completed 13ms
receipt-d79f1c1a total 3450ms | WT1 started->completed 110ms | validate_order: sched->started 3077ms started->completed 39ms | compute_total: sched->started 4ms started->completed 29ms | format_receipt: sched->started 20ms started->completed 30ms
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

One receipt has a first Workflow Task of 79 milliseconds, and the other has 110.
That is long next to the 15 milliseconds in part 2, because the thread that hashes competes with the loop thread for the GIL.
The loop is live, but the GIL is not free.
The receipts take about 3.5 seconds in total.
Most of that time is a wait of about 3 seconds for an Activity slot behind the rollup pause.
That wait does not freeze the loop.

Last, look at the **Workflow Task Execution Latency** panel again.

![The Workflow Task Execution Latency panel after the fix, with the rollup line peaking near 68 milliseconds.](../images/03-solution-live-workflow-task-latency.png)

The rollup line peaks near 68 milliseconds and the receipt line near 52 milliseconds.
That is milliseconds, where the practice panel showed seconds.
The small rise is the GIL contention you read in the receipts.

## Step 10: Adding CPU with a second Worker process

A thread cannot give you more than one core of hashing.
More CPU needs more Worker processes.
The shipped `solution/worker.py` reads its Prometheus port from `ASYNC_DEBUG_METRICS_PORT`, so a second copy needs no edit.
Leave the first Worker running on port 9464.
In a third terminal, in the `solution` directory, start the second Worker on port 9466:

```sh
ASYNC_DEBUG_METRICS_PORT=9466 uv run python worker.py
```

Both Workers poll the same Task Queue, and each prints its own PID in the banner.
In the capture, the first Worker (port 9464) is PID 2811953 and the second Worker (port 9466) is PID 2811952.
Each Worker keeps the shipped two Activity slots.

First, submit two bad runs:

```sh
uv run python starter.py --bad 2 --geo 0 --rollups 0 --receipts 0
```

This capture keeps the column header and the two process rows of one `top` reading, taken about 18 seconds into the run.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2811953 ziggy     25   5  794824  74980  31492 S  93.0   0.5   0:19.92 python
2811952 ziggy     25   5  725580  75704  31336 S   0.0   0.5   0:00.65 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The next capture is the `temporal workflow describe` output for both runs at 10 seconds.
It keeps each run's Workflow ID and the identity of the Worker that started `get_location`.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
  WorkflowId            geo-c09d5ff9-aa41-4f3a-804b-640cb1fe1598
  LastWorkerIdentity  2811953@host
  WorkflowId            geo-feb2b56c-2951-4154-af42-fdf4d0066c49
  LastWorkerIdentity  2811953@host
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

One process reads 93.0 percent and the other reads 0.0.
Both runs report the same Worker identity, `2811953@host`, and it is the busy process in the `top` capture.
They share one core, so each run takes about 63 seconds.
`temporal workflow describe` prints a RunTime field once a run closes, and this run did not save that reading.
The figure comes from a summary the capture computed over the run histories.
The summary subtracted the first event time from the last, and no tool printed it.
The second Worker ran only the short `get_ip` call for each run, and both `get_location` calls landed on the first Worker.

Now submit three bad runs:

```sh
uv run python starter.py --bad 3 --geo 0 --rollups 0 --receipts 0
```

In the capture, two runs filled the second Worker's two slots, and the third went to the first Worker.
This capture keeps the column header and the two process rows of the `top` reading from about 20 seconds in.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2811953 ziggy     25   5  875572  78512  31736 S  96.0   0.5   1:22.33 python
2811952 ziggy     25   5  944144  80464  31588 S  93.1   0.5   0:20.43 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The next capture is the `temporal workflow describe` output for the three runs at about 12 seconds.
It keeps each run's Workflow ID and Worker identity.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
  WorkflowId            geo-a10b834b-0f34-4068-91df-144786d051a1
  LastWorkerIdentity  2811953@host
  WorkflowId            geo-f69b1568-cd2e-4aca-a827-d083d1529f4d
  LastWorkerIdentity  2811952@host
  WorkflowId            geo-fe437b36-3f7d-43f6-9403-fc187e472d19
  LastWorkerIdentity  2811952@host
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The two processes read 96.0 and 93.1 percent, so the combined CPU is about 189 percent, more than one core can give.
One run, the `geo-a10b834b` Workflow, is on `2811953@host`, and the other two are on `2811952@host`.
Each Worker holds a busy `get_location`, which matches the two busy rows in `top`.
The run that had a Worker to itself finished in 30.14 seconds.
The two runs that shared a Worker took 73.53 and 73.83 seconds.
Those three figures come from the same computed summary, not from saved tool output.

In this capture, the second Worker took a `get_location` only when a third bad run arrived.
The two processes then used about 189 percent CPU together.

## Conclusion

In this tutorial, you moved a CPU-bound calculation off the event loop with a small change.
You made `get_location` a plain `def`, switched its HTTP client to the sync one, and gave the Worker a thread pool.
The loop stays live, but the hashing still holds the GIL, so one process still tops out at one core.
When you need more CPU, you add Worker processes.

The CPU reading is the new tool from this part.
It reads near zero for a call that waits and near 100 percent for a calculation, while `asyncio ps` shows the same shape for both.

In part 5, a fix that looks right runs the work twice.
Read more about Workers in the [Temporal documentation](https://docs.temporal.io/).

Next: TODO (link to part 5, "Stopping a thread that outlives its Activity attempt").
