# Fixing a sleep between heartbeats in an async Activity
<!-- TODO: venue not yet chosen. -->

### Introduction

An Activity can send a Heartbeat to tell the Temporal Service that it still runs.
In an `async def` Activity, the SDK handles that Heartbeat on the same event loop that runs your code.
If your code then blocks the loop with `time.sleep`, the Heartbeat waits in a queue and never reaches the server.

In this tutorial, you run a polling Activity that heartbeats before every wait.
You watch the server fail it on a Heartbeat timeout again and again.
You use the Web UI, `python -m asyncio ps`, `py-spy dump`, and the Worker log to find the sleep that holds the event loop.
Then you write a test that counts Heartbeats during one poll wait, replace the single sleep with awaited ticks, and run the fleet again.

This is part 3 of the series "Debugging blocking calls in Temporal async Activities".
Previous: TODO (link to part 2, "Fixing a blocking HTTP client in an async Activity").
Next: TODO (link to part 4, "Moving CPU-bound work off the event loop").

## Prerequisites

To complete this tutorial, you need:

- The setup from part 1 and the process inspection setting it describes.
- The server from `just server` and the dashboard stack from `just metrics`, both running.
- The `exercises/02-sleep-between-heartbeats` directory of the demo repository, which holds a `practice` copy with the bug and a `solution` copy with the fix.
- `py-spy`, which you run on demand with `uvx py-spy dump --pid <PID>`.

The practice copy calls the public providers with the async `httpx.AsyncClient`, so nothing in this exercise blocks on the network.

## Step 1: Running the fleet

Most lookups in this service ask a public provider and return in well under a second.
One lookup path polls a slow job instead.
The `get_location` Activity checks the job, records a Heartbeat, waits eight seconds, and checks again.
The job needs about 60 seconds to finish.

The Workflow gives that Activity a Heartbeat timeout of five seconds and no retry limit.
The Activity heartbeats before every wait, so you expect it to pass.
The same Worker also runs a `SalesRollupWorkflow` and an `OrderReceiptWorkflow`, which share nothing with the slow job.
Do not read the Activity code yet.

Change to the practice directory and start the Worker:

```sh
cd exercises/02-sleep-between-heartbeats/practice
uv run python worker.py
```

Note the PID in the banner.
In a second terminal, change to the same directory and submit the fleet:

```sh
uv run python starter.py --bad 1 --geo 1 --rollups 1 --receipts 2
```

The `--bad 1` option sends one geo run to the slow job.
The command takes about 70 seconds.
While it runs, move to Step 2.

## Step 2: Watching the retries

The healthy geo run finishes in about a second, so the geo run that is still running is the slow job.
Open the Web UI at http://localhost:8233, or list the run with the `temporal` command:

```sh
temporal workflow list \
  --query 'WorkflowType="GeoEnrichmentWorkflow" AND ExecutionStatus="Running"'
```

Open that Workflow and select the **Pending Activities** tab.
The screenshot below shows the tab about 10 seconds in.
The **Attempt** field reads `2 of Unlimited`, and **Last Failure** holds a Heartbeat timeout.

![The Web UI Pending Activities tab for the slow geo run, with get_location Scheduled on attempt 2 of Unlimited and a Heartbeat timeout as the last failure.](../images/02-practice-ui-attempt-2.png)

Reload the page about 50 seconds in.

![The same tab after about 50 seconds, with get_location Scheduled on attempt 4 of Unlimited and the same Heartbeat timeout as the last failure.](../images/02-practice-ui-attempt-4.png)

The attempt count climbs.
The Activity never stops failing, and the server keeps starting it again.
The command line shows the same thing.
Run `temporal workflow describe -w <geo workflow ID>` at about 3, 9, 31, and 48 seconds.
This capture keeps only the `State` and `Attempt` lines from each of the four describe outputs, in that order.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
  State               Started
  Attempt             1
  State               Scheduled
  Attempt             2
  State               Scheduled
  Attempt             3
  State               Scheduled
  Attempt             4
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Attempt 1 runs at 3 seconds.
Attempt 2 waits in `Scheduled` at 9 seconds, attempt 3 at 31 seconds, and attempt 4 at 48 seconds.
At 9 and 31 seconds the `ScheduledTime` has already passed.
The tasks for attempts 2 and 3 were due, and the Worker had not taken either.
A Worker with a healthy loop picks up a due Activity task right away.
At 48 seconds `ScheduledTime` still reads 1 second from now, so attempt 4 is still in its retry backoff.

This capture keeps the pending Activity section from the 9-second describe output.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Pending Activities: 1

  ActivityId          2
  Type                get_location
  State               Scheduled
  Attempt             2
  MaximumAttempts     0
  ScheduledTime       1 second ago
  ExpirationTime      2 minutes from now
  LastFailure         {"message":"activity Heartbeat timeout","source":"Server","timeoutFailureInfo":{"timeoutType":"TIMEOUT_TYPE_HEARTBEAT"}}
  LastWorkerIdentity  2772020@host
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The blocks and screenshots in Steps 2 to 5 all come from that same run.

## Step 3: Reading the starter output and the Event History

When the starter finishes, compare its output with what you expected.
This is the output from the capture of this exercise:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
rollup rollup-04fbf28c-faca-4cd2-b192-98e92244e979 FAILED: Activity task timed out
geo geo-4f8ec4a1-1fef-4b27-a937-37871f345be6: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
receipt receipt-b52b2fe6-52e4-4f98-9321-67105c069833: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-73ebe4bd-bb4d-431a-9273-9598fd2893a1: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
geo geo-9f58649c-6e27-487d-ae7a-275245123d87: GeoEnrichmentOutput(ip='256.256.256.256', location='Austin, Texas, United States')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The rollup failed with `Activity task timed out`.
The geo run for the slow job finished, but only after about 65 seconds.
The receipts finished too, and they do no I/O.
Run `temporal workflow show -w <receipt workflow ID>` for one of them.
This capture keeps the first ten lines, which hold the first eight Events of a receipt.
The times are in Coordinated Universal Time (UTC).

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Progress:
  ID           Time                     Type           
    1  2026-11-08T18:00:54Z  WorkflowExecutionStarted  
    2  2026-11-08T18:00:54Z  WorkflowTaskScheduled     
    3  2026-11-08T18:00:54Z  WorkflowTaskStarted       
    4  2026-11-08T18:01:04Z  WorkflowTaskTimedOut      
    5  2026-11-08T18:01:39Z  WorkflowTaskScheduled     
    6  2026-11-08T18:01:39Z  WorkflowTaskStarted       
    7  2026-11-08T18:01:57Z  WorkflowTaskCompleted     
    8  2026-11-08T18:01:57Z  ActivityTaskScheduled     
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The first Workflow Task started at 18:00:54.
At 18:01:04 the history shows `WorkflowTaskTimedOut`.
The Worker never replied to that first task.
The next Workflow Task started at 18:01:39 and completed at 18:01:57.
A receipt should not wait a minute for anything, so something shared is holding the Worker.

The repository ships a helper that reads each receipt's Event History and prints the Workflow Task time and the Activity waits.
Run it from the repository root with the receipt Workflow IDs from your run:

```sh
just receipt-gaps <receipt workflow ID> <receipt workflow ID>
```

This is what `just receipt-gaps` printed for the two receipts in the capture.
This capture keeps only the two receipt lines and drops the command line the capture starts with.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt-73ebe4bd total 62987ms | WT1 started->completed 62840ms | validate_order: sched->started 5ms started->completed 17ms | compute_total: sched->started 3ms started->completed 15ms | format_receipt: sched->started 6ms started->completed 11ms
receipt-b52b2fe6 total 63883ms | WT1 started->completed 62852ms | validate_order: sched->started 975ms started->completed 5ms | compute_total: sched->started 2ms started->completed 4ms | format_receipt: sched->started 3ms started->completed 4ms
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `WT1 started->completed` field runs from the start of the first Workflow Task to the completion of the first Workflow Task that completed.
In this history that spans the timed-out task and its retry, and it reads 62.8 seconds for both receipts.
The Activities in the receipts finish in milliseconds, so the stall sits in the Workflow Task.

Last, look at the Event History of the slow geo run.
Run `temporal workflow show -w <geo workflow ID>`.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Progress:
  ID           Time                     Type           
    1  2026-11-08T18:00:52Z  WorkflowExecutionStarted  
    2  2026-11-08T18:00:52Z  WorkflowTaskScheduled     
    3  2026-11-08T18:00:52Z  WorkflowTaskStarted       
    4  2026-11-08T18:00:52Z  WorkflowTaskCompleted     
    5  2026-11-08T18:00:52Z  ActivityTaskScheduled     
    6  2026-11-08T18:00:52Z  ActivityTaskStarted       
    7  2026-11-08T18:00:53Z  ActivityTaskCompleted     
    8  2026-11-08T18:00:53Z  WorkflowTaskScheduled     
    9  2026-11-08T18:00:53Z  WorkflowTaskStarted       
   10  2026-11-08T18:00:53Z  WorkflowTaskCompleted     
   11  2026-11-08T18:00:53Z  ActivityTaskScheduled     
   12  2026-11-08T18:01:58Z  ActivityTaskStarted       
   13  2026-11-08T18:01:58Z  ActivityTaskCompleted     
   14  2026-11-08T18:01:58Z  WorkflowTaskScheduled     
   15  2026-11-08T18:01:58Z  WorkflowTaskStarted       
   16  2026-11-08T18:01:58Z  WorkflowTaskCompleted     
   17  2026-11-08T18:01:58Z  WorkflowExecutionCompleted

Results:
  Status          COMPLETED
  Result          {"ip":"256.256.256.256","location":"Austin, Texas, United States"}
  ResultEncoding  json/plain
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `get_location` Activity has one `ActivityTaskScheduled` event at 18:00:53, one `ActivityTaskStarted` event at 18:01:58, and one `ActivityTaskCompleted` event.
The text output of `temporal workflow show` lists no failure here.
A retried Activity writes no event for each failed attempt, so the history cannot show the storm.
The Web UI and `describe` show it while the attempts are pending, and the Worker log shows the polls of each attempt.

You now have two clues.
The server fails an Activity that heartbeats, and it keeps retrying.
The Worker does not pick the retries up, and unrelated Workflows stall for a minute.
Replace `<PID>` with the PID from the Worker banner in the next steps.

## Step 4: Finding the stuck task and the blocking line

`python -m asyncio ps` reads the memory of the Worker from outside the process, so it answers during a freeze.
Run it from the repository root, about 10 seconds into the run:

```sh
uv run python -m asyncio ps <PID>
```

The output lists the tasks on the loop:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
tid        task id              task name            coroutine stack                                    awaiter chain                                      awaiter name    awaiter id     
------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
2772020    0x721a03fdf2f0       Task-1               Worker._run -> Worker.run -> main                                                                                     0x0            
2772020    0x721a03fdfe30       Task-2               Event.wait -> Worker._run.<locals>.raise_on_shutdown _wait -> wait                                      Task-5          0x721a03f33d90 
2772020    0x721a03e26f70       Task-3               _wait -> wait -> _ActivityWorker.run               _wait -> wait                                      Task-5          0x721a03f33d90 
2772020    0x721a03e26a00       Task-4               Worker.poll_workflow_activation -> _WorkflowWorker.run _wait -> wait                                      Task-5          0x721a03f33d90 
2772020    0x721a03f33d90       Task-5               _wait -> wait                                      Worker._run -> Worker.run -> main                  Task-1          0x721a03fdf2f0 
2772020    0x721a03f33bd0       Task-6               Queue.get -> _ActivityWorker.run.<locals>.raise_from_exception_queue _wait -> wait -> _ActivityWorker.run               Task-3          0x721a03e26f70 
2772020    0x721a03e5fcd0       Task-18              sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task                                                                    0x0            
2772020    0x721a02640500       Task-43              _ActivityWorker._handle_start_activity_task                                                                           0x0            
2772020    0x721a0279c5f0       Task-44              Worker.poll_activity_task                          _wait -> wait -> _ActivityWorker.run               Task-3          0x721a03e26f70 
2772020    0x721a026f3110       Task-47              _WorkflowWorker._handle_activation                                                                                    0x0            
2772020    0x721a03c22c60       Task-48              _ActivityWorker._heartbeat_async                                                                                      0x0            
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Look at Task-43.
Its stack ends at `_ActivityWorker._handle_start_activity_task`, the outermost call, and nothing sits beneath it.
Task-18, the rollup, waits at `sleep`, as a healthy task does.
Task-48 is `_ActivityWorker._heartbeat_async`, and it also has nothing beneath it.
The SDK uses that task to send a Heartbeat to the server.
The tool shows the shape, but it cannot name the line that blocks.

Now run `py-spy dump`, which reads the thread stacks from the operating system:

```sh
uvx py-spy dump --pid <PID>
```

This capture keeps only the `MainThread` stack.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Process 2772020: /home/ziggy/temporal-async-debug/.venv/bin/python worker.py
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 2772020 (idle): "MainThread"
    get_location (activities.py:192)
    _ActivityInboundImpl.execute_activity (temporalio/worker/_activity.py:889)
    _ActivityWorker._execute_activity (temporalio/worker/_activity.py:681)
    _ActivityWorker._handle_start_activity_task (temporalio/worker/_activity.py:351)
    Handle._run (asyncio/events.py:94)
    BaseEventLoop._run_once (asyncio/base_events.py:2046)
    BaseEventLoop.run_forever (asyncio/base_events.py:677)
    BaseEventLoop.run_until_complete (asyncio/base_events.py:706)
    Runner.run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (worker.py:113)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The top frame, the innermost call, is `get_location` at `activities.py:192`.
No `httpx` frame sits on top of it, and no socket read.
You meet the line at that number in Step 7.
The main thread runs the event loop, so that line holds the loop.
The state reads `idle` and not `active` because `time.sleep` releases the Global Interpreter Lock (GIL) while it waits.

Check the CPU with `top`:

```sh
top -b -d 1 -n 2 -p <PID> | tail -8
```

The `-n 2` option prints two frames, so the second frame reports CPU use over a real one-second interval.
This capture keeps only the column header and the process row.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2772020 ziggy     20   0  726272  77704  31800 S   0.0   0.5   0:00.72 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The Worker uses 0.0 percent of a CPU, in state `S`.
A frozen loop at near-zero CPU points to a call that waits, and `time.sleep` waits.

## Step 5: Reading the Worker log

The server failed attempt 1 about five seconds in.
The Activity prints a line on every poll, with the attempt number, so the Worker log shows what happened next.
This capture keeps only the lines that start with `[attempt`, which are the poll lines.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
[attempt 1] poll 1: job 0s of 60s
[attempt 1] poll 2: job 8s of 60s
[attempt 1] poll 3: job 16s of 60s
[attempt 1] poll 4: job 24s of 60s
[attempt 1] poll 5: job 32s of 60s
[attempt 2] poll 1: job 40s of 60s
[attempt 2] poll 2: job 48s of 60s
[attempt 2] poll 3: job 56s of 60s
[attempt 2] poll 4: job 60s of 60s
[attempt 3] poll 1: job 60s of 60s
[attempt 4] poll 1: job 60s of 60s
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Attempt 1 printed five polls, up to job time 32 seconds.
The server had failed it after about five seconds, and the attempt kept going.
It ran as a zombie until the cancel finally landed.
Attempt 2 started after that and polled through job time 60 seconds.
Attempts 3 and 4 each found the job done on their first poll.

The log also holds Temporal's own warnings about the frozen loop.
Two codes matter.
The first is `TMPRL1104`, "Workflow task duration exceeded 5 seconds".
This capture keeps only those lines.
It strips the terminal color codes and leaves every other character of each line alone.
The `workflow_task_duration` field is in milliseconds.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
2026-11-08T18:01:33.405068Z  WARN temporalio_sdk_core::worker::workflow::managed_run: [TMPRL1104] 01a1bc51-fd33-72ec-8093-b0fdf653e3e4:9:1 Workflow task duration exceeded 5 seconds. workflow_type=SalesRollupWorkflow event_id=9 attempt=1 workflow_task_duration=21095 workflow_history_size=955 payload_download_count=0 payload_download_size=0 payload_download_duration=0 payload_download_drivers=[] payload_upload_count=0 payload_upload_size=0 payload_upload_duration=0 payload_upload_drivers=[]
2026-11-08T18:01:33.411684Z  WARN temporalio_sdk_core::worker::workflow::managed_run: [TMPRL1104] 01a1bc52-0638-7e78-9b8d-29f6966887d9:4:1 Workflow task duration exceeded 5 seconds. workflow_type=OrderReceiptWorkflow event_id=4 attempt=1 workflow_task_duration=38812 workflow_history_size=381 payload_download_count=0 payload_download_size=0 payload_download_duration=0 payload_download_drivers=[] payload_upload_count=0 payload_upload_size=0 payload_upload_duration=0 payload_upload_drivers=[]
2026-11-08T18:01:49.417480Z  WARN temporalio_sdk_core::worker::workflow::managed_run: [TMPRL1104] 01a1bc52-0641-76cc-a969-585b7828372f:4:1 Workflow task duration exceeded 5 seconds. workflow_type=OrderReceiptWorkflow event_id=4 attempt=1 workflow_task_duration=54810 workflow_history_size=381 payload_download_count=0 payload_download_size=0 payload_download_duration=0 payload_download_drivers=[] payload_upload_count=0 payload_upload_size=0 payload_upload_duration=0 payload_upload_drivers=[]
2026-11-08T18:01:57.420106Z  WARN temporalio_sdk_core::worker::workflow::managed_run: [TMPRL1104] 01a1bc51-ff48-777b-825a-821ea6125f71:10:1 Workflow task duration exceeded 5 seconds. workflow_type=GeoEnrichmentWorkflow event_id=10 attempt=1 workflow_task_duration=53977 workflow_history_size=988 payload_download_count=0 payload_download_size=0 payload_download_duration=0 payload_download_drivers=[] payload_upload_count=0 payload_upload_size=0 payload_upload_duration=0 payload_upload_drivers=[]
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The four lines name the rollup, two receipts, and the geo run.
Each shows a Workflow Task that took between 21 and 55 seconds, on Workflows whose code does nothing slow.
`TMPRL1104` appeared in every capture run.

The second is `TMPRL1101`, "Potential deadlock detected".
This capture keeps only the first traceback that carries it.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Failed handling activation on workflow with run ID 01a1bc52-0641-76cc-a969-585b7828372f
Traceback (most recent call last):
  File "/home/ziggy/temporal-async-debug/.venv/lib/python3.14/site-packages/temporalio/worker/_workflow.py", line 434, in _handle_activation
    raise deadlock_exc from None
temporalio.worker._workflow._DeadlockError: [TMPRL1101] Potential deadlock detected: workflow didn't yield within 2 second(s).
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The name suggests a deadlock in your Workflow code.
Read it as a clue about the Worker instead.
The Workflow code in the capture does nothing slow, and the SDK raised the error because the Worker could not run it on time.
`TMPRL1101` appeared in all four capture runs, each time on one failed Workflow Task, but it depends on timing.
The two runs with the Web UI open also failed one legacy Query each.
Your run may not show it.
When you see it next to a `TMPRL1104`, look for something that holds the event loop.

The SDK cancels an `async def` Activity with an asyncio cancel.
That cancel lands only at an await, and `time.sleep` is not an await.
So the zombie attempt kept polling until a cancel reached it at an await.

## Step 6: Checking the dashboard

Open http://localhost:3000 and find the dashboard panels.
Two panels come from an earlier run of the same fleet, the first of the four capture runs.
Their numbers differ a little from the earlier blocks.
One of them can mislead you.

Start with **Workflow Task Execution Latency**.
It plots a 30-second rate average of Workflow Task time for each Workflow type.

![The Workflow Task Execution Latency panel during the practice run, with the receipt line near 55 seconds, the rollup line near 20 seconds, and the geo line between 16 and 18 seconds.](../images/02-practice-frozen-workflow-task-latency.png)

The receipt line starts near 55 seconds, the rollup line sits near 20 seconds, and the geo line sits between 16 and 18 seconds.
The panel averages over 30 seconds, so the real stall is longer.
Read the true length from `just receipt-gaps`, as you did in Step 3.

Now look at **Activity And Workflow Task Failures**.

![The Activity And Workflow Task Failures panel during the practice run, with one flat line for ScheduleToClose timeouts at 1.](../images/02-practice-frozen-failures.png)

This panel plots the server's `activity_timeout` counter by timeout type.
That counter does not count Heartbeat timeouts.
The only Activity timeout on the panel is the rollup's `ScheduleToClose`, a flat line at 1.
The storm of Heartbeat timeouts on the geo run does not appear.
The server's own `activity_task_timeout` counter with `timeout_type="Heartbeat"` did count them, and it reached 3 in the first capture run, but the dashboard does not plot it.
Do not read a quiet failures panel as a healthy Worker.
The Web UI, `describe`, and the Worker log show the storm that the panel misses.

Now that the tools agree, you can open the code.

## Step 7: Finding the cause in the code

Open the file `exercises/02-sleep-between-heartbeats/practice/activities.py` in your editor.
Find the `TODO PART C` comment in `get_location`, and read the loop under `if slow_job:`.
The loop polls the job, calls `activity.heartbeat()`, and then calls `time.sleep(POLL_INTERVAL_SECONDS)`.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
<!-- fmt:off -->
```python
        while True:
            poll_number += 1
            if await _job_is_done(f"{info.workflow_id}/{info.workflow_run_id}", info.attempt, poll_number):
                return JOB_RESULT
            if activity.in_activity():
                activity.heartbeat()
            # ANTIPATTERN (deliberate, for teaching): the heartbeat above is only queued on the event loop, and
            # time.sleep blocks that loop, so it cannot reach the server until the sleep ends and the 5-second
            # heartbeat timeout fires first; the cancel then lands at the next await, after the sleep, so each
            # failed attempt keeps polling as a zombie and every retry freezes the loop again. Correct: wait in
            # awaited ticks with a heartbeat per tick. Do not copy.
            # TODO PART C: replace this single blocking sleep with a wait that heartbeats and can be cancelled.
            time.sleep(POLL_INTERVAL_SECONDS)
```
<!-- fmt:on -->
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The call `activity.heartbeat()` does not block.
In an `async def` Activity, the SDK processes the Heartbeat on the event loop, which is the same loop that runs your Activity.
The call queues the Heartbeat and returns.
The next line calls `time.sleep` for eight seconds, which is longer than the five-second Heartbeat timeout.
The loop cannot run the queued Heartbeat until the sleep ends, so the timeout fires first.

Three things follow from the same cause.
The server fails the attempt and schedules the next one, which waits because the loop is busy.
Each attempt that does start sleeps again, so the loop freezes again and the retries pile up into a storm.
The cancel for a failed attempt cannot interrupt the sleep, so that attempt keeps polling as a zombie.
The receipts and the rollup stall because they share the loop.

The fix keeps the Activity `async def` and gives the loop a chance to run between Heartbeats.
You replace the one long sleep with short awaited waits.
Because the loop is free between ticks, the SDK can send the recorded Heartbeat, and a cancel lands at the await.

## Step 8: Writing a test that counts Heartbeats

You write the test before you change the code.
From the `practice` directory, run the tests:

```sh
uv run python -m pytest -o pythonpath="$PWD" tests
```

One test fails on purpose, and its stub carries a `TODO PART D` comment.
Open `tests/test_heartbeat.py` and read the comment in `test_a_poll_wait_heartbeats_and_does_not_starve_the_loop`.
It describes the test you write.
You shrink the timings in `activities.py` (`POLL_INTERVAL_SECONDS`, `TICK_SECONDS`, and `JOB_SECONDS`) with `monkeypatch`, so one poll wait spans several ticks.
You run `get_location` under `ActivityEnvironment` and count the calls to `on_heartbeat`.
A probe coroutine beside it records a timestamp every 50 milliseconds.
The test asserts at least two Heartbeats and no probe gap that reaches 0.2 seconds.

If you need a hint, the finished version is in `solution/tests/test_heartbeat.py`.
Run the tests again after you write yours.
The test fails while the Activity calls `time.sleep`, because the wait records one Heartbeat and holds the loop.

## Step 9: Replacing the sleep with awaited ticks

Open `activities.py` in the `practice` directory.
Replace the `time.sleep(POLL_INTERVAL_SECONDS)` line with a loop that works until the next poll is due.
On each pass, the loop calls `activity.heartbeat()` and then awaits `asyncio.sleep(...)` for at most `TICK_SECONDS`.
The `TICK_SECONDS` constant already exists in the file, and you need `import asyncio` at the top.
Delete the `ANTIPATTERN` comment and the `TODO PART C` comment.
The solution shows one way to write the loop:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
<!-- fmt:off -->
```python
        while True:
            poll_number += 1
            if await _job_is_done(f"{info.workflow_id}/{info.workflow_run_id}", info.attempt, poll_number):
                return JOB_RESULT
            loop = asyncio.get_running_loop()
            next_poll_at = loop.time() + POLL_INTERVAL_SECONDS
            while (remaining := next_poll_at - loop.time()) > 0:
                if activity.in_activity():
                    activity.heartbeat()
                await asyncio.sleep(min(TICK_SECONDS, remaining))
```
<!-- fmt:on -->
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The inner `while` loop runs until the next poll time.
Each pass records a Heartbeat and then awaits a short sleep, so the event loop gets a turn on every tick.
With the loop free, the SDK can send the Heartbeat.
The Activity still polls the job on the same schedule.
Run the tests a third time.
They all pass.

## Step 10: Verifying the fix

Stop the old Worker with `CTRL+C`, and start it again from the `practice` directory:

```sh
uv run python worker.py
```

Submit the same fleet from your second terminal:

```sh
uv run python starter.py --bad 1 --geo 1 --rollups 1 --receipts 2
```

This is what the starter printed in the capture of the solution copy.
Every Workflow completes, and the rollup completes this time.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
rollup rollup-9eca3e25-b9f9-4df6-9fb5-513b9d1e5b04: SalesRollupOutput(summary='Sales rollup for 2026-01: total 6030')
geo geo-21ec739d-c118-46ec-b1d9-b0bcf1b5d640: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
receipt receipt-831f837d-c2ef-4baa-bea6-715b42998619: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-50cc125e-9224-4fd2-ad30-a5e7da3f7fbe: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
geo geo-b5ef3952-ffdb-461f-8148-7eb7b1271446: GeoEnrichmentOutput(ip='256.256.256.256', location='Austin, Texas, United States')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Run `temporal workflow describe -w <geo workflow ID>` while the slow job runs.
This capture keeps the pending Activity section, about 3 seconds in.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Pending Activities: 1

  ActivityId          2
  Type                get_location
  State               Started
  Attempt             1
  MaximumAttempts     0
  ScheduledTime       1 second ago
  LastStartedTime     1 second ago
  LastHeartbeatTime   1 second ago
  ExpirationTime      2 minutes from now
  LastWorkerIdentity  2785531@host
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The Activity sits in the `Started` state on attempt 1.
The server received a Heartbeat, which the `LastHeartbeatTime` field shows.
Run the describe command several times across the job and read that field each time.
This capture keeps only the `LastHeartbeatTime` line from seven describe outputs, taken about 3, 12, 25, 34, 42, 52, and 61 seconds in.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
  LastHeartbeatTime   1 second ago
  LastHeartbeatTime   3 seconds ago
  LastHeartbeatTime   3 seconds ago
  LastHeartbeatTime   1 second ago
  LastHeartbeatTime   1 second ago
  LastHeartbeatTime   2 seconds ago
  LastHeartbeatTime   now
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The Heartbeat on the server is never more than 3 seconds old, which is far inside the five-second limit.
The attempt count stays at 1 in all seven describe outputs.

Now look at the Event History of the geo run with `temporal workflow show -w <geo workflow ID>`.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Progress:
  ID           Time                     Type           
    1  2026-11-08T18:05:07Z  WorkflowExecutionStarted  
    2  2026-11-08T18:05:07Z  WorkflowTaskScheduled     
    3  2026-11-08T18:05:07Z  WorkflowTaskStarted       
    4  2026-11-08T18:05:07Z  WorkflowTaskCompleted     
    5  2026-11-08T18:05:07Z  ActivityTaskScheduled     
    6  2026-11-08T18:05:07Z  ActivityTaskStarted       
    7  2026-11-08T18:05:07Z  ActivityTaskCompleted     
    8  2026-11-08T18:05:07Z  WorkflowTaskScheduled     
    9  2026-11-08T18:05:07Z  WorkflowTaskStarted       
   10  2026-11-08T18:05:07Z  WorkflowTaskCompleted     
   11  2026-11-08T18:05:07Z  ActivityTaskScheduled     
   12  2026-11-08T18:05:07Z  ActivityTaskStarted       
   13  2026-11-08T18:06:11Z  ActivityTaskCompleted     
   14  2026-11-08T18:06:11Z  WorkflowTaskScheduled     
   15  2026-11-08T18:06:11Z  WorkflowTaskStarted       
   16  2026-11-08T18:06:11Z  WorkflowTaskCompleted     
   17  2026-11-08T18:06:11Z  WorkflowExecutionCompleted

Results:
  Status          COMPLETED
  Result          {"ip":"256.256.256.256","location":"Austin, Texas, United States"}
  ResultEncoding  json/plain
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `get_location` Activity (events 11 to 13) has one `ActivityTaskStarted` event and one `ActivityTaskCompleted` event.
It started at 18:05:07 and completed at 18:06:11, about 64 seconds later.
No timeout and no second attempt appear.

Run `py-spy dump` again while the job runs.
This capture keeps only the `MainThread` stack.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Process 2785531: /home/ziggy/temporal-async-debug/.venv/bin/python worker.py
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 2785531 (idle): "MainThread"
    EpollSelector.select (selectors.py:452)
    BaseEventLoop._run_once (asyncio/base_events.py:2008)
    BaseEventLoop.run_forever (asyncio/base_events.py:677)
    BaseEventLoop.run_until_complete (asyncio/base_events.py:706)
    Runner.run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (worker.py:113)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `MainThread` sits in `EpollSelector.select`, which is a healthy loop waiting for work.
The solution Worker log shows each poll once.
This capture keeps only the lines that start with `[attempt`.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
[attempt 1] poll 1: job 0s of 60s
[attempt 1] poll 2: job 8s of 60s
[attempt 1] poll 3: job 16s of 60s
[attempt 1] poll 4: job 24s of 60s
[attempt 1] poll 5: job 32s of 60s
[attempt 1] poll 6: job 40s of 60s
[attempt 1] poll 7: job 48s of 60s
[attempt 1] poll 8: job 56s of 60s
[attempt 1] poll 9: job 60s of 60s
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

All nine poll lines come from attempt 1, and the job finishes at poll 9.
Neither `TMPRL1101` nor `TMPRL1104` appears in the solution log.

Now read the receipts.
This is what `just receipt-gaps` printed for the two receipts in the solution capture.
This capture keeps only the two receipt lines and drops the command line the capture starts with.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
receipt-50cc125e total 3040ms | WT1 started->completed 14ms | validate_order: sched->started 2954ms started->completed 6ms | compute_total: sched->started 4ms started->completed 5ms | format_receipt: sched->started 4ms started->completed 6ms
receipt-831f837d total 4095ms | WT1 started->completed 16ms | validate_order: sched->started 4013ms started->completed 6ms | compute_total: sched->started 4ms started->completed 5ms | format_receipt: sched->started 4ms started->completed 6ms
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `WT1 started->completed` field reads 14 and 16 milliseconds for the receipts, against 62.8 seconds in the practice run.
Each `validate_order` waits about 3 and 4 seconds for an Activity slot, while the geo runs hold both slots.
That is a wait for a free slot and does not freeze the loop.

Last, look at the **Workflow Task Execution Latency** panel again.

![The Workflow Task Execution Latency panel after the fix, with the lines at 0 milliseconds on a scale that runs to 8 seconds, and three points near 7.8 seconds at the left edge.](../images/02-solution-live-workflow-task-latency.png)

The lines sit at 0 milliseconds on a scale that runs to 8 seconds.
The three points near 7.8 seconds at the left edge sit before the solution fleet started, so they are not from the solution run.
The panel is a weak signal here, and `just receipt-gaps` gives the number.

## Conclusion

In this tutorial, you replaced one blocking sleep with a loop of awaited ticks.
Each tick gives the event loop a turn.
The Heartbeat reaches the server, a cancel can land, and the receipts and the rollup keep running.
The Activity still polls the job on the same schedule.

You found the cause with the Web UI and the server first, then with `asyncio ps`, `py-spy dump`, and the Worker log.
The first showed a climbing attempt count, and the others named the sleep that held the loop.

In part 4, the call that blocks the loop is a calculation instead of a sleep.
Read more about Activity Heartbeats in the [Temporal documentation](https://docs.temporal.io/).

Next: TODO (link to part 4, "Moving CPU-bound work off the event loop").
