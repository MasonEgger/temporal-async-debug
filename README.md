# temporal-async-debug

A Temporal Python demo that breaks on purpose, so you can practice diagnosing why a Worker stops doing work.

**Warning: this repository contains deliberately broken code, written for educational purposes only.**
**Every bug and mistuning here is a feature of the demo.**
**Do not copy any of it into a real codebase.**

This repository is the companion to a tutorial on diagnosing blocking and saturation failures in `async def` Activities.
It runs four unrelated Workflow types on one Worker, then drives one of them into a range of failure modes.
You reproduce each failure and diagnose it from outside the process, with Python 3.14's native tooling (`python -m asyncio ps` and `pstree`), `py-spy dump`, the `temporal` command-line tool, and the Temporal SDK's Prometheus metrics.
The code carries no instrumentation for the diagnosis.

Tutorial: TODO (link to the masonegger.com tutorial and longer post once published).

## The headline: one Workflow type takes down another

The four Workflow types have nothing to do with each other:

- `GeoEnrichmentWorkflow` looks up an IP address and its location over HTTP.
- `OrderReceiptWorkflow` builds a receipt in memory, instantly.
- `SalesRollupWorkflow` sums four figures after a five-second cooperative pause.
- `PriceQuoteWorkflow` computes a quote in memory and is the one sample that sets a `schedule_to_start_timeout`.

They share one Worker.
Every `async def` Activity, the Python side of Workflow Task handling, and the Python tasks that hand poll results to your code share one asyncio event loop, so they freeze together.
The SDK's Rust core does the network polling and serves the Prometheus endpoint on its own threads, so both keep going through a freeze: that is why the server keeps dispatching tasks that then time out, and why `asyncio ps` and the metrics endpoint still answer.
So when one geo Activity misbehaves, the rollups, receipts, and quotes fail or stall too, even though their code is correct.
Nothing in their code or their Event History names the cause.
You find it with the tooling in the lessons below.

The two root causes look the same from a Workflow's point of view but differ in the tools:

- A frozen event loop: something blocks or burns CPU on the loop and nothing else on that loop can run.
- A saturated Worker: the loop is healthy, but every Activity slot is full, so queued work waits.

## The diagnostic story: two tools for a frozen loop

A frozen loop takes two tools to diagnose, because each one answers a different question.

- `python -m asyncio ps` and `pstree` show the shape of the freeze, with zero instrumentation.
  The wedged Activity task dead-ends at the SDK frame `_ActivityWorker._handle_start_activity_task`, with no `await` beneath it.
  Every other task sits parked at a real `await`, such as `sleep`, `wait`, or `Queue.get`.
- `py-spy dump` names the exact blocking line.
  It shows `_apply_mode` at the `time.sleep` call in `activities.py`.

`asyncio ps` cannot show the blocking line, and that is not a bug in the tool.
It rebuilds each task from its chain of awaits.
A task stuck in synchronous code is not suspended at an await, so its frames live on the operating system thread stack instead.
`py-spy` reads that thread stack.

Two more readings finish the diagnosis:

- CPU separates the two freeze causes: near zero for a blocking call, because `time.sleep` releases the Global Interpreter Lock (GIL), and 100 percent for CPU-bound code, because the loop holds the GIL.
- A saturated Worker looks different.
  Every task sits at a healthy await, none is dead-ended, and the backlog age in `temporal task-queue describe` keeps climbing.

Two readings do not tell the two families (frozen loop, saturated Worker) apart.
`temporal_worker_task_slots_available` reads 0 during part of a freeze and during saturation, so zero free slots only says the slot pool is full.
The poller `LastAccessTime` in `temporal task-queue describe` is not a freeze signal at all, because the pollers live in the SDK's Rust core and keep long-polling through a freeze.

## Quickstart

You need Python 3.14 or newer, [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just), and the [Temporal CLI](https://docs.temporal.io/cli).
The inspecting Python and the Worker's Python must both be 3.14 or newer, and `uv run` gives you that.
The lessons also use `py-spy`, which this repository does not install.
Run it on demand with `uvx py-spy dump --pid <PID>`.
Open three terminals in the repository.

Terminal 1, the local Temporal dev server:

```bash
just server
```

Terminal 2, the Worker:

```bash
just worker
```

The Worker prints a banner with its PID and the exact introspection commands.
This is the banner from one capture session (your PID will differ):

```text
========================================================================
temporal-async-debug worker running with PID 717532
Inspect the live event loop from another terminal with either of:
    python -m asyncio ps 717532
    python -m asyncio pstree 717532
Prometheus metrics: http://127.0.0.1:9464/metrics
========================================================================
```

Terminal 3, a scenario recipe.
Start with the healthy fleet:

```bash
just healthy
```

Bare `just` prints every recipe:

| Recipe | What it does |
|---|---|
| `just healthy` | Full fleet (two geo, a rollup, three receipts, a quote), all completing |
| `just trigger` | Smaller healthy fleet (geo and receipts only), a quick smoke test |
| `just block [seconds]` | A geo run calls `time.sleep` and freezes the loop, with a healthy geo, a rollup, and two receipts alongside (default 30) |
| `just cpu [seconds]` | A geo run spins in a busy loop and freezes the loop, with the same fleet as `block` (default 30) |
| `just slow [seconds]` | Two geo runs hold both Activity slots with `asyncio.sleep`, with a healthy geo, a rollup, two receipts, and a quote queued behind them (default 30) |
| `just slow-heartbeat [seconds]` | Two geo runs hold both slots but heartbeat correctly, with a rollup and two receipts queued behind them (default 30) |
| `just stuck [seconds]` | A geo run waits without heartbeating and trips its heartbeat timeout, with a healthy geo alongside (default 30) |

The Temporal Web UI is at http://localhost:8233.
Each geo run has two Activities (`get_ip`, then `get_location`), and both apply the delay, so a 30-second scenario holds for about 60 seconds.

### About the captured output

Everything quoted in the lessons is real output, captured in October 2026 against `temporal server start-dev` (Temporal CLI 1.6.2, server 1.30.2) with `temporalio` 1.33.0 on Python 3.14.3, Linux.
The captures came from several Worker runs, so task numbers, addresses, PIDs, and Workflow IDs differ between excerpts.

These are the only edits made to the captures:

- Runs of spaces in `asyncio ps` tables are collapsed to two spaces, and the dashed rule under the header is dropped.
- Rows that are identical in every capture are omitted from some `ps` excerpts, and each such excerpt says so.
  These are the housekeeping tasks Task-1 through Task-6: Task-1 through Task-5 belong to the SDK's `Worker.run`, and Task-6 is the `_ActivityWorker.run` exception-queue task.
- Absolute paths in `pstree` are trimmed to the package-relative form that `py-spy` already prints, such as `temporalio/bridge/worker.py:226` or `temporal_async_debug/rollup.py:48`.
  The package prefix stays, so the SDK's `temporalio/bridge/worker.py` cannot be confused with this repository's `temporal_async_debug/worker.py`.
  `pstree` excerpts show only the branches the text names; the housekeeping tree under Task-1 is omitted.
- `py-spy dump` output is unedited, except that the two idle pool threads (`temporal_workflow__0` and `asyncio_0`) are omitted where a lesson says so, and Lessons 2 and 3 show a few frames on their own, again where the text says so.
- Where one block combines readings from several snapshots, each line carries a label such as `t+8:` or `before:` that is not part of the tool's output.
- Workflow IDs in starter output are shortened to their first eight hex digits followed by `...`.
- Prometheus label sets are shortened to `{...}`, keeping `worker_type` where it matters.
- `temporal task-queue describe` excerpts drop the JSON block the capture script requested after the table.
- Lines that the capture script added (the command echo, start and end markers, exit codes) are removed.
  In Lessons 2, 3, and 7 the capture script's timestamp prefix on each starter line is kept, because the timing is the point, and it is not part of the starter's own output.

No number, name, or message inside a quoted line was changed.

## Lesson 1: a healthy Worker

Run `just healthy`.
Every run completes, and this is the full output:

```text
geo geo-ecff0e03-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-8af29f2a-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
receipt receipt-b491dd60-...: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-66b37b09-...: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
receipt receipt-6e155a01-...: OrderReceiptOutput(receipt='order order-2: 59.97 USD')
rollup rollup-a10d86ec-...: SalesRollupOutput(summary='Sales rollup for 2026-01: total 6030')
quote quote-8b3cb66f-...: PriceQuoteOutput(quote='Quote for 1 x SKU-0: 9.99 USD')
```

An idle Worker's `python -m asyncio ps <PID>` shows every task parked on an asyncio suspension point.
This excerpt keeps the Activity poller row (housekeeping rows omitted):

```text
tid  task id  task name  coroutine stack  awaiter chain  awaiter name  awaiter id
3114262  0x72e104070710  Task-7  Worker.poll_activity_task  _wait -> wait -> _ActivityWorker.run  Task-3  0x72e10419abd0
```

The matching `pstree` branch ends in `Worker.poll_activity_task`, the Python side of the Worker waiting on the Temporal server for its next Activity:

```text
                            │               └── (T) Task-7
                            │                   └──  Worker.poll_activity_task temporalio/bridge/worker.py:226
```

`py-spy dump` shows the main thread idle in the event loop's `select` call, waiting for I/O:

```text
Process 3114262: /home/ziggy/temporal-async-debug/.venv/bin/python3 -m temporal_async_debug.worker
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 3114262 (idle): "MainThread"
    select (selectors.py:452)
    _run_once (asyncio/base_events.py:2008)
    run_forever (asyncio/base_events.py:677)
    run_until_complete (asyncio/base_events.py:706)
    run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (temporal_async_debug/worker.py:124)
    _run_code (<frozen runpy>:88)
    _run_module_as_main (<frozen runpy>:199)
```

The healthy readings to remember:

- CPU: low, in state `S` (sleeping).
  `ps -o pid,%cpu,stat,etime,wchan -p <PID>` printed `3114262  3.7 SNl        00:13 ep_poll`.
  The `%CPU` column of `ps` is an average over the process lifetime, so this number includes startup.
- Slots: `temporal_worker_task_slots_available` for `worker_type="ActivityWorker"` reads 2 (the Worker is sized with `max_concurrent_activities=2`).
- Latency: `temporal_activity_schedule_to_start_latency` has a small sum and count after the healthy run (a sum of 1130 milliseconds across a count of 15).

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 2
temporal_activity_schedule_to_start_latency_sum{...} 1130
temporal_activity_schedule_to_start_latency_count{...} 15
```

No timeout fires.

Now that you have the healthy baseline, the next two lessons freeze the loop and compare each reading against it.

## Lesson 2: a frozen loop from a blocking call

Run `just block`.
In `activities.py`, the `block` mode calls `time.sleep` inside an `async def`.
The line looks harmless, and it carries the antipattern marker (see [Finding the deliberate bugs](#finding-the-deliberate-bugs)).

The bad geo run freezes the loop twice.
Its first Activity, `get_ip`, calls `time.sleep(30)`, and so does its second, `get_location`.
Between the two freezes the loop runs for only a fraction of a second (60 to 570 ms across 8 captured runs, depending on how long `get_ip`'s HTTP call takes).
So a 30-second `just block` keeps the Worker frozen for about 60 seconds, and the starter's wall time was 61 to 62 seconds in every captured run.

### How the starter sequences the fleet

The starter submits the runs in a fixed order, so the same thing fails every time:

1. It submits the rollup and the healthy geo run, and waits for the healthy geo to finish.
   The healthy geo completed in 0.15 to 0.33 seconds in all 8 runs, before the bad run was submitted.
   It survives because the starter waits for it, not because of its 120-second `start_to_close`.
2. It submits the bad geo run.
   The rollup is still inside its five-second pause, so it is in flight when the first freeze lands.
3. It waits until the server reports the bad run's second Activity, `get_location`, as STARTED, then waits one more second.
4. It submits the receipts (and quotes, when requested), so they arrive during the final freeze.

Step 3 waits for the second Activity on purpose.
A bystander released into the short thaw between the two freezes can be dispatched just as the loop freezes again, and then it fails.
That happened to 1 of 16 bystanders when the starter waited only for `get_ip` to start, in a run with 138 ms of live loop between the freezes.

### The CPU, the metrics endpoint, and the slots

While the freeze is active, run the introspection commands from another terminal.
`asyncio ps` and `py-spy` both work because they read process memory without running code in it.

The metrics scrape stays fast.
The SDK's Rust core serves the endpoint off the event loop, so a reachable endpoint tells you nothing about the loop.
Every scrape during the final captured freezes answered in 0.7 to 1.7 ms (earlier captures took 11 to 25 ms, still fast).
Do not use it as the frozen-loop signal.

The CPU is near zero, because `time.sleep` releases the GIL and the process sleeps inside a system call.
Eight seconds into the freeze, `ps -o pid,%cpu,stat,etime,wchan -p <PID>` printed:

```text
    PID %CPU STAT     ELAPSED WCHAN
3114262  1.7 SNl        00:38 hrtimer_nanosleep
```

The state is `S` (sleeping) and the kernel wait channel is `hrtimer_nanosleep`, the system call `time.sleep` waits in.
The `%CPU` column is a lifetime average.
An earlier `top` capture during a freeze, which measures the current interval, read `0.0` in state `S`:

```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2379759 ziggy     25   5  871712  81120  31868 S   0.0   0.5   0:00.99 python3
```

The slots gauge changes partway through the freeze.
These are the readings at 8, 20, and 40 seconds after the bad run started:

```text
t+8:  temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
t+20: temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
t+40: temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 1
```

During the first freeze, the frozen `get_ip` and the in-flight rollup hold both slots.
The rollup's slot is reclaimed at the first thaw, so during the second freeze only the frozen `get_location` holds one.
Zero free slots shows up in both families (the saturation lessons read 0 too), so the gauge cannot tell you which one you have.
The `asyncio ps` shape and the CPU reading can.

### The shape: `asyncio ps` and `pstree`

The first tool is `python -m asyncio ps <PID>`.
This is what it printed eight seconds into the freeze (housekeeping rows omitted):

```text
tid  task id  task name  coroutine stack  awaiter chain  awaiter name  awaiter id
3114262  0x72e1042b7bd0  Task-6  Queue.get -> _ActivityWorker.run.<locals>.raise_from_exception_queue _wait -> wait -> _ActivityWorker.run  Task-3  0x72e10419abd0
3114262  0x72e10420b750  Task-18  sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
3114262  0x72e103f625d0  Task-37  _ActivityWorker._handle_start_activity_task  0x0
3114262  0x72e103f62990  Task-38  Worker.poll_activity_task  _wait -> wait -> _ActivityWorker.run  Task-3  0x72e10419abd0
```

Here is how to read it:

- Task-37 is the wedged task.
  Its stack stops at the SDK frame `_ActivityWorker._handle_start_activity_task`, with no suspension point beneath it.
  A task that is parked always ends on an await such as `sleep`, `wait`, or `Queue.get`, and this one does not.
- Task-18 is the `roll_up_sales` Activity parked on `sleep`.
  Its timer is the five-second pause, and on a frozen loop that timer cannot fire.
- Task-6 and Task-38 are parked at real awaits, but the loop that would wake them is stuck.

The `pstree` view from the same moment shows the same thing as branches:

```text
└── (T) Task-18
    └──  _ActivityWorker._handle_start_activity_task temporalio/worker/_activity.py:351
        └──  _ActivityWorker._execute_activity temporalio/worker/_activity.py:681
            └──  _ActivityInboundImpl.execute_activity temporalio/worker/_activity.py:889
                └──  roll_up_sales temporal_async_debug/rollup.py:48
                    └──  sleep asyncio/tasks.py:702
└── (T) Task-37
    └──  _ActivityWorker._handle_start_activity_task temporalio/worker/_activity.py:351
```

Task-18 ends on `sleep`, at `rollup.py:48`.
Task-37 ends on the SDK handler and nothing else.
That is the frozen-loop shape.

It does not name the file.
No frame in Task-37 points at `activities.py`.
That is the limit described in [the diagnostic story](#the-diagnostic-story-two-tools-for-a-frozen-loop): the blocking call is synchronous, so it is not on the asyncio stack.

### The line: `py-spy dump`

The second tool is `py-spy dump --pid <PID>`, which reads the OS thread stack.
Run it with `uvx py-spy dump --pid <PID>`, using the Worker's own Python PID (the `.venv` `python3`, not the `uv` wrapper process).
This is the dump from the same freeze, eight seconds in (pool threads omitted):

```text
Process 3114262: /home/ziggy/temporal-async-debug/.venv/bin/python3 -m temporal_async_debug.worker
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 3114262 (idle): "MainThread"
    _apply_mode (temporal_async_debug/activities.py:142)
    get_ip (temporal_async_debug/activities.py:196)
    execute_activity (temporalio/worker/_activity.py:889)
    _execute_activity (temporalio/worker/_activity.py:681)
    _handle_start_activity_task (temporalio/worker/_activity.py:351)
    _run (asyncio/events.py:94)
    _run_once (asyncio/base_events.py:2046)
    run_forever (asyncio/base_events.py:677)
    run_until_complete (asyncio/base_events.py:706)
    run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (temporal_async_debug/worker.py:124)
    _run_code (<frozen runpy>:88)
    _run_module_as_main (<frozen runpy>:199)
```

The top frame is `_apply_mode` at `activities.py:142`, which is the `time.sleep` call.
The frames below it are the same SDK chain that `asyncio ps` stopped at (`_handle_start_activity_task`, `_activity.py:351`), now continued down into your code.
The `idle` label means the thread is not holding the GIL, which matches the near-zero CPU.

During the second freeze, 40 seconds in, the same dump has `get_location` where `get_ip` was:

```text
    _apply_mode (temporal_async_debug/activities.py:142)
    get_location (temporal_async_debug/activities.py:225)
```

### The server's view: pollers and backlog

`temporal task-queue describe --task-queue async-debug-task-queue` lists the Worker's pollers with a `LastAccessTime`.
It is tempting to read a frozen Worker as one that stops polling.
It does not.
The pollers live in the SDK's Rust core, off the event loop, and they keep long-polling through a freeze.

These are the poller rows at 8, 20, and 40 seconds into the freeze:

```text
t+8:
  UNVERSIONED  activity       3114262@host  7 seconds ago          100000
  UNVERSIONED  workflow       3114262@host  7 seconds ago          100000
t+20:
  UNVERSIONED  workflow       3114262@host  19 seconds ago         100000
  UNVERSIONED  activity       3114262@host  19 seconds ago         100000
t+40:
  UNVERSIONED  workflow       3114262@host  7 seconds ago          100000
  UNVERSIONED  activity       3114262@host  8 seconds ago          100000
```

An idle, healthy Worker's ages cycle from 0 to about 59 seconds with the 60-second long poll, so every one of these readings looks normal.
The t+40 ages are low for two different reasons.
The Activity poller polled again during the short thaw between the two freezes.
The Workflow poller polled again when the server dispatched the receipts' Workflow Task to it, about 1.3 seconds into the second freeze, while the loop was still frozen.
That mid-freeze poll is the clearest evidence that the pollers keep working through a freeze.
The Worker never left the Pollers list in any capture, including one taken 75 seconds into a frozen run.

The backlog in the same command is more useful, but it also needs care.
At t+20 the table showed one Activity task waiting:

```text
Task Queue Statistics:
    BuildID    TaskQueueType  ApproximateBacklogCount  ApproximateBacklogAge  BacklogIncreaseRate  TasksAddRate  TasksDispatchRate
  UNVERSIONED  workflow                             0  0s                          -2.0384789e-05    0.15181327         0.15183365
  UNVERSIONED  activity                             1  8.909193706s                   0.050182194    0.25278533         0.20260313
```

That task is the rollup's retry, which the server scheduled after the first attempt timed out and which no slot could take.
A backlog appears whenever no Activity slot is free, in a freeze or in saturation.
It is the live saturation tell in Lesson 4, and here it is one more sign that the slots are full, not that the loop is frozen.

Together the tools give the full answer.
`asyncio ps` says the loop is frozen and which task is wedged.
`py-spy` says the line.
The CPU reading then separates this case from the next one.

### What fails

This is the starter's output, with the capture script's timestamps:

```text
23:14:46.222 rollup rollup-a7298337-... FAILED: Activity task timed out
23:14:46.224 geo geo-3d51ff3d-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
23:15:15.115 receipt receipt-38055a87-...: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
23:15:15.134 receipt receipt-d77ac5f0-...: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
23:15:15.138 geo geo-6e55ea18-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```

The starter printed the healthy geo's result after the rollup's failure, even though the healthy geo had finished more than 30 seconds earlier.

The rollup was in flight when the freeze landed, so its Workflow fails.
It failed this way in 8 of 8 captured `block` and `cpu` runs.
The starter's message does not say which timeout fired.
`temporal workflow show --workflow-id <id>` does:

```text
Progress:
  ID           Time                     Type           
    1  2026-10-07T23:14:13Z  WorkflowExecutionStarted  
    2  2026-10-07T23:14:13Z  WorkflowTaskScheduled     
    3  2026-10-07T23:14:13Z  WorkflowTaskStarted       
    4  2026-10-07T23:14:13Z  WorkflowTaskCompleted     
    5  2026-10-07T23:14:13Z  ActivityTaskScheduled     
    6  2026-10-07T23:14:33Z  ActivityTaskTimedOut      
    7  2026-10-07T23:14:33Z  WorkflowTaskScheduled     
    8  2026-10-07T23:14:33Z  WorkflowTaskStarted       
    9  2026-10-07T23:14:43Z  WorkflowTaskTimedOut      
   10  2026-10-07T23:14:43Z  WorkflowTaskScheduled     
   11  2026-10-07T23:14:43Z  WorkflowTaskStarted       
   12  2026-10-07T23:14:44Z  WorkflowTaskCompleted     
   13  2026-10-07T23:14:44Z  WorkflowExecutionFailed   

Results:
  Status   FAILED
  Failure  
    Message: Activity task timed out
    Cause:
        Message: activity ScheduleToClose timeout
        Cause:
            Message: activity StartToClose timeout
```

The rollup's Activity sets a 10-second `start_to_close` and a 20-second `schedule_to_close`, and keeps the default retry policy.
The first attempt hit `start_to_close` on the frozen Worker.
The default retry policy scheduled a second attempt, which waited in the backlog with no free slot until the 20-second `schedule_to_close` ran out.
So the top-level timeout is `ScheduleToClose` and its cause is `StartToClose`.
The `WorkflowTaskTimedOut` at event 9 is the frozen loop again: the Workflow Task that would record the failure went to the frozen Worker and timed out.

The receipts stall instead of failing.
They arrive during the second freeze, so the frozen Worker cannot process their first Workflow Task, and their Activities are not even scheduled until the thaw.
All 19 receipts and quotes in the 8 captured runs completed at the thaw, after 28.85 to 29.12 seconds, with no Activity timeouts and no failures.
This is one receipt's history:

```text
Progress:
  ID           Time                     Type           
    1  2026-10-07T23:14:46Z  WorkflowExecutionStarted  
    2  2026-10-07T23:14:46Z  WorkflowTaskScheduled     
    3  2026-10-07T23:14:46Z  WorkflowTaskStarted       
    4  2026-10-07T23:14:56Z  WorkflowTaskTimedOut      
    5  2026-10-07T23:15:06Z  WorkflowTaskScheduled     
    6  2026-10-07T23:15:06Z  WorkflowTaskStarted       
    7  2026-10-07T23:15:15Z  WorkflowTaskCompleted     
    8  2026-10-07T23:15:15Z  ActivityTaskScheduled     
    9  2026-10-07T23:15:15Z  ActivityTaskStarted       
   10  2026-10-07T23:15:15Z  ActivityTaskCompleted     
   11  2026-10-07T23:15:15Z  WorkflowTaskScheduled     
   12  2026-10-07T23:15:15Z  WorkflowTaskStarted       
   13  2026-10-07T23:15:15Z  WorkflowTaskCompleted     
   14  2026-10-07T23:15:15Z  ActivityTaskScheduled     
   15  2026-10-07T23:15:15Z  ActivityTaskStarted       
   16  2026-10-07T23:15:15Z  ActivityTaskCompleted     
   17  2026-10-07T23:15:15Z  WorkflowTaskScheduled     
   18  2026-10-07T23:15:15Z  WorkflowTaskStarted       
   19  2026-10-07T23:15:15Z  WorkflowTaskCompleted     
   20  2026-10-07T23:15:15Z  ActivityTaskScheduled     
   21  2026-10-07T23:15:15Z  ActivityTaskStarted       
   22  2026-10-07T23:15:15Z  ActivityTaskCompleted     
   23  2026-10-07T23:15:15Z  WorkflowTaskScheduled     
   24  2026-10-07T23:15:15Z  WorkflowTaskStarted       
   25  2026-10-07T23:15:15Z  WorkflowTaskCompleted     
   26  2026-10-07T23:15:15Z  WorkflowExecutionCompleted

Results:
  Status          COMPLETED
  Result          {"receipt":"order order-0: 59.97 USD"}
  ResultEncoding  json/plain
```

The first Workflow Task timed out on the frozen Worker after 10 seconds (`WorkflowTaskTimedOut` at event 4).
The retry also landed on the frozen Worker and completed at 23:15:15, the thaw.
Every Activity after that ran in the same second.
Every captured receipt and quote had exactly one `WorkflowTaskTimedOut`: its first Workflow Task, handed to the frozen Worker, expired, and the retry succeeded at the thaw.

The bad geo run itself completes, after about 60 seconds.
That is the cross-type damage: a geo bug failed a rollup that has no bug, and held up receipts for half a minute.

## Lesson 3: a frozen loop from CPU-bound code

Run `just cpu`.
The `cpu` mode spins in a `while time.monotonic() < deadline` loop with no `await`.
The freeze, the starter's sequencing, and the collateral damage are the same as in Lesson 2.
The CPU reading is the difference.

This `top` row is one sample from a `just cpu` freeze:

```text
2379759 ziggy     25   5  878992  88268  32020 R 100.0   0.5   0:05.97 python3
```

The state column reads `R` (running) and `%CPU` reads `100.0`.
The process sat between 81.8 and 100 percent in all 24 samples taken while the freeze was active.
The `ps` snapshot eight seconds into the first `cpu` run of the final capture session agrees: the state is `R` and there is no kernel wait channel, where Lesson 2 showed `S` and `hrtimer_nanosleep`:

```text
    PID %CPU STAT     ELAPSED WCHAN
3114262  3.0 RNl        04:32 -
```

(The `3.0` is again a lifetime average, diluted by the minutes the Worker spent idle before the run.)
This is the shared-GIL case: the busy loop holds the GIL, so the thread never goes idle.
The metrics endpoint still answers, and the slots read 0 at t+8 and t+20 and 1 at t+40, as in Lesson 2.

`asyncio ps` has the same shape as Lesson 2: a stale `sleep -> roll_up_sales` row and a running task cut off at `_ActivityWorker._handle_start_activity_task` (housekeeping rows omitted):

```text
tid  task id  task name  coroutine stack  awaiter chain  awaiter name  awaiter id
3114262  0x72e1026fb200  Task-345  sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
3114262  0x72e101b1da90  Task-364  _ActivityWorker._handle_start_activity_task  0x0
3114262  0x72e101b1f020  Task-365  Worker.poll_activity_task  _wait -> wait -> _ActivityWorker.run  Task-3  0x72e10419abd0
```

`py-spy dump` names the line, and it also shows the CPU case in its thread label.
This is the top of the main thread's dump eight seconds into the `just cpu` freeze:

```text
Thread 3114262 (active+gil): "MainThread"
    _apply_mode (temporal_async_debug/activities.py:148)
    get_ip (temporal_async_debug/activities.py:196)
    execute_activity (temporalio/worker/_activity.py:889)
    _execute_activity (temporalio/worker/_activity.py:681)
    _handle_start_activity_task (temporalio/worker/_activity.py:351)
```

The line is `activities.py:148`, which is the `while time.monotonic() < deadline` loop.
The label is `active+gil` where the `block` dump said `idle`, so the thread is running and holds the GIL.

The failure is the same as Lesson 2:

```text
23:18:39.162 rollup rollup-769a255d-... FAILED: Activity task timed out
23:18:39.166 geo geo-671ae9fa-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
23:19:08.051 receipt receipt-15a021b7-...: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
23:19:08.060 receipt receipt-50ef62c7-...: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
23:19:08.064 geo geo-9efe55ca-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```

The rollup's `temporal workflow show` failure has the same chain, `ScheduleToClose` caused by `StartToClose`, and the receipts complete at the thaw.

The two freeze lessons differ in one reading:

| | `block` | `cpu` |
|---|---|---|
| CPU | near 0 percent, state `S`, waiting in `hrtimer_nanosleep` | 81.8 to 100 percent, state `R` |
| `asyncio ps` | stale parked tasks plus one task dead-ended at the SDK handler | same |
| `py-spy dump` | `activities.py:142` (`time.sleep`), thread `idle` | `activities.py:148` (the busy loop), thread `active+gil` |
| Slots gauge | 0 during the `get_ip` freeze, 1 during the `get_location` freeze | same |
| Metrics endpoint | reachable | reachable |

Now that you can recognize a frozen loop, the next lesson shows the other family, where the loop is healthy and the slots are the problem.

## Lesson 4: slot exhaustion

Run `just slow`.
Two geo runs await `asyncio.sleep(30)` in each Activity, holding both slots.
The loop is healthy the whole time.
The starter submits the two hogging runs first, waits until the slots gauge reads 0, and then submits a healthy geo run, a rollup, two receipts, and a quote.

The process is in state `S` (sleeping), with no task burning CPU.
The slots gauge reads 0:

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
```

`asyncio ps` looks healthy.
Both hogging Activities are parked on `sleep`, a suspension point, and the full call chain is visible down to your code (housekeeping rows omitted):

```text
tid  task id  task name  coroutine stack  awaiter chain  awaiter name  awaiter id
717532  0x794b6d1b2d50  Task-333  sleep -> _apply_mode -> get_ip -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
717532  0x794b6c4515e0  Task-335  sleep -> _apply_mode -> get_ip -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
717532  0x794b6c4517c0  Task-336  Worker.poll_activity_task  _wait -> wait -> _ActivityWorker.run  Task-3  0x794b6ee8ebd0
```

This is the contrast with Lessons 2 and 3.
Here the stacks are complete and end on `sleep`, and no task is dead-ended at the SDK handler.

### The backlog is the live tell

The Worker does not take new Activity tasks while every slot is full, so work queues on the server.
`temporal task-queue describe --task-queue async-debug-task-queue` showed the backlog 25 seconds into the hold:

```text
Task Queue Statistics:
    BuildID    TaskQueueType  ApproximateBacklogCount  ApproximateBacklogAge  BacklogIncreaseRate  TasksAddRate  TasksDispatchRate
  UNVERSIONED  workflow                             0  0s                          -1.0803342e-05     0.2227049          0.2227157
  UNVERSIONED  activity                             3  24.037671824s                   0.15920892    0.22288218        0.063673265
Pollers:
    BuildID    TaskQueueType   Identity   LastAccessTime  RatePerSecond
  UNVERSIONED  workflow       717532@host  24 seconds ago         100000
  UNVERSIONED  activity       717532@host  24 seconds ago         100000
```

Across snapshots at 8, 15, and 25 seconds, the Activity backlog read 5 tasks at 7.1 seconds, 3 at 14.1 seconds, and 3 at 24.0 seconds.
The age keeps climbing for as long as every slot stays full.
The count is approximate and lags, because expired tasks stay in the matching backlog until a poller drains them, so do not read each drop as one timeout.
That climbing backlog age is the live saturation tell.

The poller ages in the same snapshots read 7, 14, and 24 seconds.
The Activity poller's age grows here because the Worker does not ask for another Activity task while zero slots are free.
An idle Worker's age also climbs to about 59 seconds on every long poll, so a growing age is at most a weak hint.
Read the backlog age instead.

### What fails

The starved bystanders fail, and the healthy geo run finishes late:

```text
receipt receipt-d622ecf0-... FAILED: Activity task timed out
receipt receipt-8a5eeaaf-... FAILED: Activity task timed out
rollup rollup-add50434-... FAILED: Activity task timed out
quote quote-ff1cf213-... FAILED: Activity task timed out
geo geo-306154cc-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-a728c9c2-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-c4c1d9a7-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```

`temporal workflow show` gives the cause.
This is one receipt:

```text
Progress:
  ID           Time                     Type           
    1  2026-10-04T17:41:17Z  WorkflowExecutionStarted  
    2  2026-10-04T17:41:17Z  WorkflowTaskScheduled     
    3  2026-10-04T17:41:17Z  WorkflowTaskStarted       
    4  2026-10-04T17:41:17Z  WorkflowTaskCompleted     
    5  2026-10-04T17:41:17Z  ActivityTaskScheduled     
    6  2026-10-04T17:41:27Z  ActivityTaskTimedOut      
    7  2026-10-04T17:41:27Z  WorkflowTaskScheduled     
    8  2026-10-04T17:41:27Z  WorkflowTaskStarted       
    9  2026-10-04T17:41:27Z  WorkflowTaskCompleted     
   10  2026-10-04T17:41:27Z  WorkflowExecutionFailed   

Results:
  Status   FAILED
  Failure  
    Message: Activity task timed out
    Cause:
        Message: activity ScheduleToStart timeout
```

The rollup and the quote show the same `ScheduleToStart` cause.
The quote failed 5 seconds after its Activity was scheduled, the receipts after 10, and the rollup after 20.

The receipt and rollup set `start_to_close` and `schedule_to_close`, but no `schedule_to_start`, and the server still labeled the failure `ScheduleToStart`.
When `schedule_to_start` is unset, the server copies `schedule_to_close` into it.
You can see the copy in the `ActivityTaskScheduled` event attributes.
These two lines come from an earlier `slow` run, as printed by the capture script's digest of the Event History JSON:

```text
  5 16:32:03.642 ACTIVITY_TASK_SCHEDULED {'scheduleToCloseTimeout': '10s', 'scheduleToStartTimeout': '10s', 'startToCloseTimeout': '5s', 'heartbeatTimeout': '0s'} retry: {'initialInterval': '1s', 'backoffCoefficient': 2, 'maximumInterval': '100s'}
  5 16:32:03.652 ACTIVITY_TASK_SCHEDULED {'scheduleToCloseTimeout': '20s', 'scheduleToStartTimeout': '20s', 'startToCloseTimeout': '10s', 'heartbeatTimeout': '0s'} retry: {'initialInterval': '1s', 'backoffCoefficient': 2, 'maximumInterval': '100s'}
```

The first line is a receipt (10s and 10s), the second the rollup (20s and 20s).
Both timers share one deadline, and a task that is still queued when it arrives gets the `ScheduleToStart` label.
Read the label as "never got a slot".

The label flips to `ScheduleToClose` only if a slot frees in the final milliseconds before the deadline.
That happened once, in a 12-second `slow` run, where one receipt started about 3 ms before its 10-second deadline (same digest format):

```text
===== receipt-5a90dc01-9a85-47e3-8d72-c5807c141d41
  1 16:40:11.565822 WORKFLOW_EXECUTION_STARTED
  5 16:40:11.588875 ACTIVITY_TASK_SCHEDULED
  6 16:40:21.586083 ACTIVITY_TASK_STARTED
  7 16:40:21.590267 ACTIVITY_TASK_TIMED_OUT {"message": "activity ScheduleToClose timeout", "source": "Server", "timeoutFailureInfo": {"timeoutType": "TIMEOUT_TYPE_SCHEDULE_TO_CLOSE"}} RETRY_STATE_NON_RETRYABLE_FAILURE
  11 16:40:21.607430 WORKFLOW_EXECUTION_FAILED
```

The healthy geo run survives because its `schedule_to_close` is 150 seconds.
It queued behind the hold and completed after 59.88 seconds.
Each of its two Activities waited about 30 seconds to start (29.98 and 29.70 seconds of schedule-to-start latency).

### The latency metric lags

`temporal_activity_schedule_to_start_latency` is recorded when a queued task finally starts.
A task that times out in the queue never records a value.
Under `just slow`, the sum jumped once the late healthy geo started, because it recorded its two waits of about 30 seconds.
Before and after the run:

```text
before: temporal_activity_schedule_to_start_latency_sum{...} 3464
before: temporal_activity_schedule_to_start_latency_count{...} 27
after:  temporal_activity_schedule_to_start_latency_sum{...} 63530
after:  temporal_activity_schedule_to_start_latency_count{...} 33
```

Snapshots at 8, 15, and 25 seconds into the hold all read 3472, so the metric said nothing while the jam was live.
Under `just slow-heartbeat` (Lesson 5), which has no healthy geo, nothing queued ever starts, and the sum barely moved, from 63530 to 63543.
Read the backlog age first, because it is live.
The latency metric confirms the saturation afterward, and only for work that eventually got a slot.

The fix is different from Lessons 2 and 3.
Do not touch the event loop.
Size the Worker for the load (raise `max_concurrent_activities`, add Workers) or move long work off this Task Queue.

The next lesson holds both slots the same way, with code that does everything right.

## Lesson 5: a correct long-running Activity (`slow_heartbeat`)

Run `just slow-heartbeat`.
The `slow_heartbeat` mode is the right way to hold a slot for legitimately long work.
It awaits `asyncio.sleep` in 3-second steps and calls `activity.heartbeat` between steps, and the Workflow sets a 10-second `heartbeat_timeout` that each heartbeat satisfies.
This is the one mode with no antipattern marker.

The tool output looks like Lesson 4:

- `asyncio ps` shows both Activities parked on `sleep -> _apply_mode -> get_ip -> ...`.
- The process is in state `S`.
- The Activity backlog age climbs: 3 tasks at 7.1 seconds, then 1 at 14.1 seconds, then 1 at 24.1 seconds.
- The slots gauge reads 0 and `temporal_worker_task_slots_used` for the ActivityWorker reads 2:

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
temporal_worker_task_slots_used{...,worker_type="ActivityWorker"} 2
```

Both geo runs complete, and the bystanders still starve:

```text
receipt receipt-36f70d87-... FAILED: Activity task timed out
receipt receipt-e957a769-... FAILED: Activity task timed out
rollup rollup-1850b362-... FAILED: Activity task timed out
geo geo-133f0eeb-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-43d48c74-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```

Each bystander fails with the same `ScheduleToStart` cause as in Lesson 4.

The lesson: correct code on an undersized Worker still starves other work.
No heartbeat timeout fires here.
The fix is the Worker's size, not the Activity.

Now that you have seen a long Activity that heartbeats, the next lesson takes the heartbeat away.

## Lesson 6: a heartbeat timeout (`stuck_no_heartbeat`)

Run `just stuck`.
The `stuck_no_heartbeat` mode awaits one long `asyncio.sleep` and never heartbeats, while the Workflow sets the same 10-second `heartbeat_timeout` as Lesson 5.
The loop is healthy, and `asyncio ps` shows a parked Activity (housekeeping rows omitted):

```text
tid  task id  task name  coroutine stack  awaiter chain  awaiter name  awaiter id
717532  0x794b6c4534d0  Task-507  sleep -> _apply_mode -> get_ip -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
717532  0x794b6c451400  Task-521  Worker.poll_activity_task  _wait -> wait -> _ActivityWorker.run  Task-3  0x794b6ee8ebd0
```

One slot is in use and one is free, five seconds in:

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 1
temporal_worker_task_slots_used{...,worker_type="ActivityWorker"} 1
```

The healthy geo run alongside it completes, and the stuck run fails 10 seconds in, not 30:

```text
geo geo-42800aa9-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-a8a0c732-... FAILED: Activity task timed out
```

The stuck run's `temporal workflow show` history names the timeout:

```text
Progress:
  ID           Time                     Type           
    1  2026-10-04T17:43:59Z  WorkflowExecutionStarted  
    2  2026-10-04T17:43:59Z  WorkflowTaskScheduled     
    3  2026-10-04T17:43:59Z  WorkflowTaskStarted       
    4  2026-10-04T17:43:59Z  WorkflowTaskCompleted     
    5  2026-10-04T17:43:59Z  ActivityTaskScheduled     
    6  2026-10-04T17:43:59Z  ActivityTaskStarted       
    7  2026-10-04T17:44:09Z  ActivityTaskTimedOut      
    8  2026-10-04T17:44:09Z  WorkflowTaskScheduled     
    9  2026-10-04T17:44:09Z  WorkflowTaskStarted       
   10  2026-10-04T17:44:09Z  WorkflowTaskCompleted     
   11  2026-10-04T17:44:09Z  WorkflowExecutionFailed   

Results:
  Status   FAILED
  Failure  
    Message: Activity task timed out
    Cause:
        Message: activity Heartbeat timeout
```

The Activity started at 17:43:59 and timed out at 17:44:09.
The `heartbeat_timeout` turned a silent hang into a fast, named failure, which is why long Activities should heartbeat and set one.

The last lesson looks closer at the quote, the bystander that failed first in Lesson 4.

## Lesson 7: the schedule-to-start sample

`PriceQuoteWorkflow` is the one place `schedule_to_start_timeout` is set (5 seconds, marked as an antipattern in `quote.py`), because a stale price quote is worthless.
You do not run a separate recipe.
The quote rides along in `just slow`, and `just healthy` runs it too, where it finishes instantly.
`just slow-heartbeat` does not submit a quote.

With every slot held, the quote cannot start, and it fails first, after 5 seconds, before the receipts (10) and the rollup (20):

```text
quote quote-ff1cf213-... FAILED: Activity task timed out
```

Its `temporal workflow show` history:

```text
Progress:
  ID           Time                     Type           
    1  2026-10-04T17:41:17Z  WorkflowExecutionStarted  
    2  2026-10-04T17:41:17Z  WorkflowTaskScheduled     
    3  2026-10-04T17:41:17Z  WorkflowTaskStarted       
    4  2026-10-04T17:41:17Z  WorkflowTaskCompleted     
    5  2026-10-04T17:41:17Z  ActivityTaskScheduled     
    6  2026-10-04T17:41:22Z  ActivityTaskTimedOut      
    7  2026-10-04T17:41:22Z  WorkflowTaskScheduled     
    8  2026-10-04T17:41:22Z  WorkflowTaskStarted       
    9  2026-10-04T17:41:22Z  WorkflowTaskCompleted     
   10  2026-10-04T17:41:22Z  WorkflowExecutionFailed   

Results:
  Status   FAILED
  Failure  
    Message: Activity task timed out
    Cause:
        Message: activity ScheduleToStart timeout
```

This is the one timeout that is a direct statement about the Worker, not about the Activity.
The Activity ran for zero seconds.
It fails fast and visibly when the Worker falls behind, and a stale quote is the rare case where you want exactly that.

A frozen loop does not trip it.
Running the `block` fleet with a quote (`uv run python -m temporal_async_debug.starter --mode block --block-seconds 30 --bad 1 --geo 1 --rollups 1 --receipts 2 --quotes 1`) gave this output:

```text
23:21:06.043 rollup rollup-99bbca70-... FAILED: Activity task timed out
23:21:06.049 geo geo-6fcc5ff6-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
23:21:34.965 receipt receipt-b91566e0-...: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
23:21:34.973 receipt receipt-ed1d9ab8-...: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
23:21:34.980 quote quote-c0372ab9-...: PriceQuoteOutput(quote='Quote for 1 x SKU-0: 9.99 USD')
23:21:34.983 geo geo-7bdbcdce-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```

The quote completed at the thaw in all 3 such runs.
The frozen Worker never processed the quote's first Workflow Task, so its Activity was not scheduled until the thaw, and the schedule-to-start clock had not started.

## Which timeout fires, and how to tell

| Mode (recipe) | Family | What fails | Timeout in the failure | CPU | `asyncio ps` | `py-spy dump` | Slots gauge |
|---|---|---|---|---|---|---|---|
| healthy | none | nothing | none | low, state `S` | all parked | main thread idle in `select` | 2 free |
| `block` | frozen loop | in-flight rollup fails; receipts and quotes stall, then complete at the thaw | `ScheduleToClose` caused by `StartToClose` | near 0, state `S` | one task dead-ended at the SDK handler, the rest parked | `activities.py:142` (`time.sleep`), thread `idle` | 0 during the `get_ip` freeze, 1 during `get_location` |
| `cpu` | frozen loop | same as `block` | same as `block` | 81.8 to 100 percent, state `R` | same as `block` | `activities.py:148` (busy loop), thread `active+gil` | same as `block` |
| `slow` | saturated Worker | rollup, receipts, quote fail; healthy geo completes late | `ScheduleToStart` | low, state `S` | every task parked, stacks end on `sleep` | not needed | 0 |
| `slow_heartbeat` | saturated Worker | rollup, receipts | `ScheduleToStart` | low, state `S` | every task parked, stacks end on `sleep` | not needed | 0 |
| `stuck_no_heartbeat` | heartbeat loss | the geo run itself | `Heartbeat` | low, state `S` | parked, stack ends on `sleep` | not needed | 1 free |
| quote sample (in `slow`) | saturated Worker | quote first | `ScheduleToStart` (5 s) | low, state `S` | every task parked | not needed | 0 |

The split to remember:

- Frozen loop (`block`, `cpu`): the metrics endpoint and the pollers keep working anyway, so they cannot help.
  The tell is the `asyncio ps` shape (one task dead-ended at `_ActivityWorker._handle_start_activity_task`, the rest parked at awaits) and the CPU reading (near 0 for `block`, 100 percent for `cpu`).
  `py-spy dump` then names the exact line in `activities.py`.
- Saturated Worker (`slow`, `slow_heartbeat`): the loop is healthy.
  Every task is parked at a healthy await and none is dead-ended, and the Task Queue shows a backlog whose age keeps climbing.
  The schedule-to-start latency histogram records the wait only once queued work finally starts.
- Slots at 0 appear in both families, and poller `LastAccessTime` cycles normally in both, so neither one tells them apart.

## Realistic timeouts, and what the demo leaves out

The timeouts in this repository follow the shape real code uses:

- `start_to_close_timeout` is set on every Activity.
  It bounds one attempt.
- `schedule_to_close_timeout` is set where an SLA fits.
  It bounds the whole call, including queue time and retries.
- `schedule_to_start_timeout` is rare.
  It appears once, in the quote sample, because failing a late start is a decision most code should not make.
- `heartbeat_timeout` appears only on the long-running modes, because a quick Activity would not heartbeat.

The backlog age in `temporal task-queue describe` is the live saturation tell.
`temporal_activity_schedule_to_start_latency` is a lagging confirmation, because it only records once a queued task starts.
Watch both in production instead of relying on a `schedule_to_start_timeout`.

The demo sets no Workflow-level timeouts.
Whether a Workflow succeeds is a question of correctness, not of elapsed time, and a Workflow timeout would end a Workflow that would have recovered.
The Activity timeouts are where the symptoms show up.

Two of the geo settings are tuned for the demo and should not be copied:

- The geo Activities use a generous 120-second `start_to_close` so that `slow` and `slow_heartbeat` hold their slots for the whole delay.
- The geo Activities set `maximum_attempts=1` (the marked antipattern in `workflow.py`), so the first failure surfaces instead of being retried past.

The receipt, rollup, and quote Activities keep the default retry policy.
Lesson 2 depends on that: the rollup's `ScheduleToClose` failure with a `StartToClose` cause exists because the default policy scheduled a second attempt.

`maximum_attempts=1` looks like exactly-once, but it is at-most-one dispatch.
If a transient failure happens before the call, the operation never runs and the Workflow fails.
If a Worker finishes the side effect but crashes before recording completion, the effect is done while the Workflow sees a failure.
Activities are at-least-once, so keep retries and make the Activity idempotent, with a stable key such as `workflow_run_id` plus `activity_id`.
That gives effectively-once side effects.
Cap attempts only when a duplicate is worse than a loss and the loss is handled.

## Platform gotchas

- **Python 3.14 or newer on both sides.**
  The inspector (the Python that runs `python -m asyncio ps`) and the target Worker must both be 3.14 or newer.
  `uv run python -m asyncio ps <PID>` uses the project's 3.14.
- **Linux Yama.**
  The default `kernel.yama.ptrace_scope=1` blocks the inspector from a sibling process.
  For `asyncio ps` the failure message is `Failed to find the PyRuntime section`.
  Run the command with `sudo`, or lower the setting with `sudo sysctl kernel.yama.ptrace_scope=0`.
  `py-spy` needs the same ptrace access.
  Without it, `py-spy dump` printed this on the capture machine before `ptrace_scope` was lowered:

  ```text
  Permission Denied: Try running again with elevated permissions by going 'sudo env "PATH=$PATH" !!'
  ```

  The capture machine had `ptrace_scope` at 0 for the final captures, so the `PyRuntime` error is the documented behavior and was not reproduced here.
- **macOS.**
  Attaching to another process requires `sudo`, for both `asyncio ps` and `py-spy`.
- **Transient failures.**
  Python 3.14's `asyncio ps` can fail on a single call, for example when a task changes while it reads memory.
  Run it again.

## Finding the deliberate bugs

Every deliberately wrong line, setting, or pattern carries a marker comment of this exact form, on or immediately above the offending line:

```text
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```

Find them all:

```bash
grep -rn "ANTIPATTERN (deliberate, for teaching)" src
```

That finds six markers: `time.sleep`, the CPU-bound loop, `stuck_no_heartbeat`, the quote's `schedule_to_start_timeout`, `max_concurrent_activities=2`, and the geo Activities' `maximum_attempts=1`.
The `slow_heartbeat` mode is correct and has no marker.
The marker labels the bad pattern for anyone, human or tool, who reads a source file without this README.

## Development

The toolchain is `uv`, `ruff`, `mypy` in strict mode, and `pytest`, run through `just`:

```bash
just check   # ruff check, ruff format --check, mypy strict, pytest
just fmt     # ruff format and ruff check --fix
just test    # pytest only
```

Tests never need a running Temporal server.
They use the SDK's `ActivityEnvironment` and `WorkflowEnvironment.start_time_skipping()`, and all network calls are mocked.
The live failure signatures in the lessons above are captured by hand, not asserted in CI.

## License

MIT.
