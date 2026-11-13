# temporal-async-debug

A Temporal Python demo that breaks on purpose, so you can practice diagnosing why a Worker stops doing work.

**Warning: this repository contains deliberately broken code, written for educational purposes only.**
**Every bug and mistuning here is a feature of the demo.**
**Do not copy any of it into a real codebase.**

The code teaches one mechanism, so it bends settings and shapes to make one point visible.
Exercises 01 to 05 reproduce each failure on a single Worker with two Activity slots, so one blocking call fails in plain view.
A real fleet has more Workers and more slots, and it can hide the same failure behind its healthy Workers.
Exercise 06 (`exercises/06-finding-the-frozen-worker`) shows that.
Nothing here is a template for a production system.

This repository is the companion to the tutorial series "Debugging blocking calls in Temporal async Activities".
The series teaches one mechanism: a call that blocks the asyncio event loop in an `async def` Activity, and how you find it.
You reproduce the failure, then diagnose it from outside the process.
You use Python 3.14's native tooling (`python -m asyncio ps` and `pstree`), `py-spy dump`, the `temporal` command-line tool, and the Temporal SDK's Prometheus metrics.
The code carries no instrumentation for the diagnosis.

If you are new to the asyncio event loop, start with the optional primer [Understanding the asyncio event loop in a Temporal Worker](docs/drafts/event-loop-primer.md).
It explains how `await` hands control back to the loop, what a blocking call does to it, and which parts of a Temporal Worker share it.

Series: TODO (add the link when the series goes up).

## What is in this repository

The repository has four layers:

- The root package, `src/temporal_async_debug/`, is the reference.
  It runs three unrelated Workflow types on one Worker and can freeze that Worker two ways.
  The three lessons below use it.
- `exercises/` holds six exercises, each with a `practice/` copy that carries a bug and a `solution/` copy that fixes it.
  See [Exercises](#exercises).
- `scripts/` holds `receipt_gaps.py`, a standard-library helper that reads receipt Event Histories.
  The `just receipt-gaps` recipe runs it.
- `observability/` holds a Prometheus and Grafana stack that plots the Worker's metrics.
  See [Observability](#observability).

## The headline: one Workflow type takes down another

The three Workflow types have nothing to do with each other:

- `GeoEnrichmentWorkflow` looks up an IP address and its location over HTTP.
- `OrderReceiptWorkflow` builds a receipt in memory, instantly.
- `SalesRollupWorkflow` sums four figures after a five-second cooperative pause.

They share one Worker.
Every `async def` Activity, the Python side of Workflow Task handling, and the Python tasks that hand poll results to your code share one asyncio event loop, so they freeze together.
The SDK's Rust core does the network polling and serves the Prometheus endpoint on its own threads, so both keep going through a freeze.
That is why the server keeps dispatching tasks that then time out, and why the metrics endpoint still answers.
So when one geo Activity blocks the loop, the rollups and receipts fail or stall too, even though their code is correct.
Nothing in their code or their Event History names the cause.
You find it with the tooling in the lessons below.

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

One more reading finishes the diagnosis.
CPU separates the two freeze causes.
The reading is near zero for a blocking call, because `time.sleep` releases the Global Interpreter Lock (GIL).
The reading is near 100 percent for CPU-bound code, because the busy loop holds the GIL.

Three readings do not point at a frozen loop.
`temporal_worker_task_slots_available` reads 0 whenever both Activity slots are in use, so it only says the slot pool is full.
The Prometheus endpoint answers in milliseconds during a freeze.
The poller `LastAccessTime` in `temporal task-queue describe` climbs during a freeze, but it climbs to 52 and 57 seconds on an idle Worker too, so it does not point at the freeze.

## Quickstart

You need Python 3.14 or newer, [uv](https://docs.astral.sh/uv/), [just](https://github.com/casey/just), and the [Temporal command-line tool](https://docs.temporal.io/cli).
The inspecting Python and the Worker's Python must both be 3.14 or newer, and `uv run` gives you that.
The lessons also use `py-spy`, which this repository does not install.
Run it on demand with `uvx py-spy dump --pid <PID>`.
Open three terminals in the repository.

Terminal 1, the local Temporal dev server:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```bash
just server
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

This runs `temporal server start-dev --metrics-port 9465`.
The extra flag makes the dev server export its own metrics, which the [Observability](#observability) section uses.

Terminal 2, the Worker:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```bash
just worker
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The Worker prints a banner with its PID and the exact introspection commands.
This is the banner from the capture session (your PID will differ):

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
========================================================================
temporal-async-debug worker running with PID 2541958
Inspect the live event loop from another terminal with either of:
    python -m asyncio ps 2541958
    python -m asyncio pstree 2541958
Prometheus metrics: http://127.0.0.1:9464/metrics
========================================================================
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Terminal 3, a scenario recipe.
Start with the healthy fleet:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```bash
just healthy
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Bare `just` prints every recipe:

| Recipe | What it does |
|---|---|
| `just server` | Start the local Temporal dev server with `--metrics-port 9465` |
| `just worker` | Start the demo Worker and print its PID for asyncio introspection |
| `just healthy` | Full healthy fleet (two geo, a rollup, three receipts), all completing |
| `just trigger` | Smaller healthy fleet (geo and receipts only), a quick smoke test |
| `just block [seconds]` | A geo run calls `time.sleep` and freezes the loop, with a healthy geo, a rollup, and two receipts alongside (default 30) |
| `just cpu [seconds]` | A geo run spins in a busy loop and freezes the loop, with the same fleet as `block` (default 30) |
| `just receipt-gaps [ids]` | Print the first Workflow Task time and the Activity waits for receipt Workflows; `--by-identity` adds the Worker identity to each line and a summary line per identity, and `--summary` prints the summary lines alone (needs the Temporal CLI and a server) |
| `just metrics` | Start Prometheus and Grafana in the background (docker-compose v1) |
| `just metrics-down` | Stop the Prometheus and Grafana stack |
| `just check` | The full gate: ruff, ruff format, mypy, and pytest on the root package, then the solution loop |
| `just check-solutions` | The solution loop alone: each `exercises/*/solution` gets ruff, ruff format, mypy, and pytest from its own directory |
| `just check-practice` | Ruff and mypy on each `exercises/*/practice` copy |
| `just preflight` | Verify the prose toolchain (Vale, the styles, the content-design and voice plugin files) |
| `just lint-prose [files]` | Run Vale on the named Markdown files, or on every committed prose file, and print JSON |
| `just lint-keyboard [files]` | Flag characters that are not on a keyboard, such as em-dashes and smart quotes |
| `just fmt` | Run `ruff format` and `ruff check --fix` |
| `just test` | Run `pytest` on the root package only |

The Temporal Web UI is at http://localhost:8233.
Each geo run has two Activities (`get_ip`, then `get_location`), and both apply the delay, so a 30-second scenario holds for close to a minute.

### About the captured output

Everything quoted in the lessons is real output, captured on 2026-11-03 against `temporal server start-dev --metrics-port 9465` (Temporal CLI 1.6.2, server 1.30.2).
The Worker ran `temporalio` 1.33.0 on Python 3.14.3, Linux.
The three lessons come from three runs of the same Worker process, so task numbers, addresses, and Workflow IDs differ between excerpts.
The Event Histories in Lesson 2 come from a fourth run, a `just block` on 2026-11-08, so their Workflow IDs match no other excerpt.
The Worker log in [Recognizing a blocked event loop](#recognizing-a-blocked-event-loop) and the latency-panel readings in [Observability](#observability) come from a fifth run, a `just block` on 2026-11-11.

These are the only edits made to the captures:

- Excerpts drop the capture script's command echo and the downloader's messages, which are not tool output.
- `asyncio ps` excerpts drop the dashed rule under the header and the housekeeping rows Task-1 through Task-6.
  Task-1 through Task-5 belong to the SDK's `Worker.run`, and Task-6 is the `_ActivityWorker.run` exception-queue task.
- `pstree` excerpts trim absolute paths to the package-relative form that `py-spy` prints.
  The package prefix stays, so `temporalio/bridge/worker.py` cannot be confused with `temporal_async_debug/worker.py`.
- `pstree` excerpts show only the branches the text names.
- `py-spy dump` excerpts omit the three idle pool threads.
- The receipt Event History excerpt keeps the first seven events of 26.
- The Worker log excerpt drops the terminal color codes (ANSI escapes) from the lines it keeps.
- `ziggy`, `256.256.256.256`, and `Milky Way Galaxy` are stand-ins for the user name, public IP address, and location of the capture machine.
  The user name appears in the `top` USER column and in paths under `/home/ziggy`.
  Your own output shows your own values.

Apart from those stand-ins, no number, name, or message inside a quoted line was changed.

## Lesson 1: a healthy Worker

Run `just healthy`.
Every run completes, and this is the full output:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
geo geo-74813b62-3f00-4d30-9377-d54f8236a39d: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-4f15bc80-6e64-4f1b-a373-ab3c4f6ba7b8: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
receipt receipt-cca1bdc1-70f9-4314-b898-6cd5d0daf537: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-a44f7d50-276b-4a16-a83a-6a80661b9a68: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
receipt receipt-7a2ad40d-52b4-4cda-81bc-13482b78af8a: OrderReceiptOutput(receipt='order order-2: 59.97 USD')
rollup rollup-1cc154ba-bd3d-4871-9b14-e6c81a0f1727: SalesRollupOutput(summary='Sales rollup for 2026-01: total 6030')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

An idle Worker's `python -m asyncio ps <PID>` shows every task parked on an asyncio suspension point.
This excerpt keeps the header and the Activity poller row:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
tid        task id              task name            coroutine stack                                    awaiter chain                                      awaiter name    awaiter id     
2541958    0x7838e706c710       Task-7               Worker.poll_activity_task                          _wait -> wait -> _ActivityWorker.run               Task-3          0x7838e7196bd0 
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The matching `pstree` branch ends in `Worker.poll_activity_task`, the Python side of the Worker waiting on the Temporal server for its next Activity:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
                            │               └── (T) Task-7
                            │                   └──  Worker.poll_activity_task temporalio/bridge/worker.py:226
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

While `just healthy` runs, the rollup's Activity is parked on a `sleep`.
The same table shows it, with a poller row beside it:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
tid        task id              task name            coroutine stack                                    awaiter chain                                      awaiter name    awaiter id     
2541958    0x7838e56375c0       Task-56              sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task                                                                    0x0            
2541958    0x7838e6f57d40       Task-109             Worker.poll_activity_task                          _wait -> wait -> _ActivityWorker.run               Task-3          0x7838e7196bd0 
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The rollup row runs from `sleep` down to the SDK handler, so the task is suspended at an await.
A parked task always ends on an await such as `sleep`, `wait`, or `Queue.get`.
Remember this shape, because the next lesson shows a task that does not have it.

Two more readings complete the baseline.
The first is the CPU, which is low and in state `S` (sleeping).
This `top` row is from the idle Worker:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2541958 ziggy     25   5  937844  78660  31612 S   0.0   0.5   0:00.94 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The second is the slots gauge.
`temporal_worker_task_slots_available` for `worker_type="ActivityWorker"` reads 2, because the Worker is sized with `max_concurrent_activities=2`:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
temporal_worker_task_slots_available{namespace="default",service_name="temporal-core-sdk",task_queue="async-debug-task-queue",worker_type="ActivityWorker"} 2
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

No timeout fires.
Now that you have the healthy baseline, the next two lessons freeze the loop and compare each reading against it.

## Lesson 2: a frozen loop from a blocking call

Run `just block`.
The `get_ip` and `get_location` Activities both call a helper, `_apply_mode`, before their HTTP request.
In `block` mode, the helper calls `time.sleep` on the event loop.
The line looks harmless, and it carries the antipattern marker (see [Finding the deliberate bugs](#finding-the-deliberate-bugs)).

The bad geo run freezes the loop twice.
Its first Activity, `get_ip`, sleeps for 30 seconds, and so does its second, `get_location`.
Between the two freezes the loop runs for a fraction of a second.
So a 30-second `just block` keeps the Worker frozen for close to a minute.
The starter took about 62 seconds end to end in the capture.

### How the starter sequences the fleet

The starter submits the runs in a fixed order, so the same thing fails every time:

1. It submits the rollup and the healthy geo run, and waits for the healthy geo to finish.
   It survives because the starter waits for it, not because of its 120-second `start_to_close`.
2. It submits the bad geo run.
   The rollup is still inside its five-second pause, so it is in flight when the first freeze lands.
3. It waits until the server reports the bad run's second Activity, `get_location`, as started, then waits one more second.
4. It submits the receipts, so they arrive during the final freeze.

Step 3 waits for the second Activity on purpose.
A bystander released into the short thaw between the two freezes can be dispatched just as the loop freezes again, and then it fails.

### The shape: `asyncio ps` and `pstree`

While the freeze is active, run the introspection commands from another terminal.
`asyncio ps` and `py-spy` both work because they read process memory without running code in it.
The first tool is `python -m asyncio ps <PID>`.
This is what it printed 14 seconds after the starter began, during the first freeze:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
tid        task id              task name            coroutine stack                                    awaiter chain                                      awaiter name    awaiter id     
2541958    0x7838e58d5130       Task-132             sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task                                                                    0x0            
2541958    0x7838e6f57d40       Task-151             _ActivityWorker._handle_start_activity_task                                                                           0x0            
2541958    0x7838e6f55130       Task-152             Worker.poll_activity_task                          _wait -> wait -> _ActivityWorker.run               Task-3          0x7838e7196bd0 
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Here is how to read it:

- Task-151 is the wedged task.
  Its stack stops at the SDK frame `_ActivityWorker._handle_start_activity_task`, with no suspension point beneath it.
  A parked task always ends on an await, and this one does not.
- Task-132 is the `roll_up_sales` Activity parked on `sleep`.
  Its timer is the five-second pause, and on a frozen loop that timer cannot fire.
- Task-152 is parked at a real await, but the loop that would wake it is stuck.

The `pstree` view from the same moment shows the same thing as branches:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
└── (T) Task-132
    └──  _ActivityWorker._handle_start_activity_task temporalio/worker/_activity.py:351
        └──  _ActivityWorker._execute_activity temporalio/worker/_activity.py:681
            └──  _ActivityInboundImpl.execute_activity temporalio/worker/_activity.py:889
                └──  roll_up_sales temporal_async_debug/rollup.py:48
                    └──  sleep asyncio/tasks.py:702
└── (T) Task-151
    └──  _ActivityWorker._handle_start_activity_task temporalio/worker/_activity.py:351
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Task-132 ends on `sleep`, at `rollup.py:48`.
Task-151 ends on the SDK handler and nothing else.
That is the frozen-loop shape.

It does not name the file.
No frame in Task-151 points at `activities.py`.
That is the limit described in [the diagnostic story](#the-diagnostic-story-two-tools-for-a-frozen-loop): the blocking call is synchronous, so it is not on the asyncio stack.

### The line: `py-spy dump`

The second tool is `py-spy dump --pid <PID>`, which reads the OS thread stack.
Run it with `uvx py-spy dump --pid <PID>`, using the Worker's own Python PID (the `.venv` `python`, not the `uv` wrapper process).
This is the dump from the same freeze:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Process 2541958: /home/ziggy/temporal-async-debug/.venv/bin/python -m temporal_async_debug.worker
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 2541958 (idle): "MainThread"
    _apply_mode (temporal_async_debug/activities.py:121)
    get_ip (temporal_async_debug/activities.py:145)
    _ActivityInboundImpl.execute_activity (temporalio/worker/_activity.py:889)
    _ActivityWorker._execute_activity (temporalio/worker/_activity.py:681)
    _ActivityWorker._handle_start_activity_task (temporalio/worker/_activity.py:351)
    Handle._run (asyncio/events.py:94)
    BaseEventLoop._run_once (asyncio/base_events.py:2046)
    BaseEventLoop.run_forever (asyncio/base_events.py:677)
    BaseEventLoop.run_until_complete (asyncio/base_events.py:706)
    Runner.run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (temporal_async_debug/worker.py:118)
    _run_code (<frozen runpy>:88)
    _run_module_as_main (<frozen runpy>:198)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The top frame is `_apply_mode` at `activities.py:121`, which is the `time.sleep` call.
The frames below it are the same SDK chain that `asyncio ps` stopped at (`_handle_start_activity_task`, `_activity.py:351`), now continued down into your code.
The `idle` label means the thread is not holding the GIL, which matches the near-zero CPU.

### The CPU, the metrics endpoint, and the slots

The CPU is near zero, because `time.sleep` releases the GIL and the process sleeps inside a system call.
`top` measures the current interval, and it read `0.0` in state `S`:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2541958 ziggy     25   5  939304  80412  31612 S   0.0   0.5   0:01.03 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `%CPU` column of `ps` is an average over the process lifetime, so it includes startup and idle time.
It read 1.2 for the same moment, which agrees:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID %CPU STAT     ELAPSED CMD
2541958  1.2 SNl        01:21 /home/ziggy/temporal-async-debug/.venv/bin/python -m temporal_async_debug.worker
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The slots gauge reads 0 free and 2 used, because the frozen `get_ip` and the in-flight rollup hold both slots:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
temporal_worker_task_slots_available{namespace="default",service_name="temporal-core-sdk",task_queue="async-debug-task-queue",worker_type="ActivityWorker"} 0
temporal_worker_task_slots_used{namespace="default",service_name="temporal-core-sdk",task_queue="async-debug-task-queue",worker_type="ActivityWorker"} 2
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

A second scrape about 8 seconds later, still inside the first freeze, read the same.
The metrics scrape stays fast.
The SDK's Rust core serves the endpoint off the event loop, so a reachable endpoint tells you nothing about the loop.
The scrape during this freeze took 0.014 seconds:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
real	0m0.014s
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Do not use the endpoint as the frozen-loop signal.
Zero free slots does not name the cause either.
The `asyncio ps` shape and the CPU reading do.

### What fails

This is the starter's output:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
rollup rollup-6a6b9770-857c-40ea-a40c-f5bc2cebc670 FAILED: Activity task timed out
geo geo-9fc45420-7790-4618-88db-3950cfed0ae6: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
receipt receipt-6ff3f1aa-b9ea-4f1e-902f-4c25464d65f7: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-930ebdbc-1230-49df-a5ec-76b98a18de66: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
geo geo-ec790305-9af6-490a-88ac-c1f473d13c72: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The rollup was in flight when the freeze landed, so its Workflow fails.
The starter's message does not say which timeout fired.
The Event History does.
These Event Histories come from a separate `just block` run on 2026-11-08, so their Workflow IDs and times differ from the excerpts above.
Run `temporal workflow show -w <rollup workflow ID>` for the rollup:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Progress:
  ID           Time                     Type           
    1  2026-11-08T18:11:27Z  WorkflowExecutionStarted  
    2  2026-11-08T18:11:27Z  WorkflowTaskScheduled     
    3  2026-11-08T18:11:27Z  WorkflowTaskStarted       
    4  2026-11-08T18:11:27Z  WorkflowTaskCompleted     
    5  2026-11-08T18:11:27Z  ActivityTaskScheduled     
    6  2026-11-08T18:11:47Z  ActivityTaskTimedOut      
    7  2026-11-08T18:11:47Z  WorkflowTaskScheduled     
    8  2026-11-08T18:11:47Z  WorkflowTaskStarted       
    9  2026-11-08T18:11:57Z  WorkflowTaskTimedOut      
   10  2026-11-08T18:11:57Z  WorkflowTaskScheduled     
   11  2026-11-08T18:11:57Z  WorkflowTaskStarted       
   12  2026-11-08T18:11:58Z  WorkflowTaskCompleted     
   13  2026-11-08T18:11:58Z  WorkflowExecutionFailed   

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

The Activity was scheduled at event 5 and timed out at event 6, 20 seconds later.
The Results block reads `ScheduleToClose` caused by `StartToClose`.
The history writes no event for a retried attempt, so it cannot tell you how many attempts ran.
The rollup's own Workflow Task stalled too.
Event 8 started it, event 9 timed it out, and a second Workflow Task completed at event 12.

The receipts stall instead of failing.
They arrive during the final freeze, so the frozen Worker cannot process their first Workflow Task.
Run the same command for a receipt:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Progress:
  ID           Time                     Type           
    1  2026-11-08T18:11:59Z  WorkflowExecutionStarted  
    2  2026-11-08T18:11:59Z  WorkflowTaskScheduled     
    3  2026-11-08T18:11:59Z  WorkflowTaskStarted       
    4  2026-11-08T18:12:09Z  WorkflowTaskTimedOut      
    5  2026-11-08T18:12:19Z  WorkflowTaskScheduled     
    6  2026-11-08T18:12:19Z  WorkflowTaskStarted       
    7  2026-11-08T18:12:28Z  WorkflowTaskCompleted     
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

This excerpt keeps the first seven events and drops events 8 through 26 and the Results block.
Event 3 starts the first Workflow Task, and event 4 records it as `WorkflowTaskTimedOut`.
The server schedules a second Workflow Task at event 5, and it completes at event 7, 29 seconds after event 3.
That is a stall across two Workflow Tasks, not one long one.

`just receipt-gaps` prints the same stall as one number.
Pass it the receipt Workflow IDs from your run:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```bash
just receipt-gaps <receipt workflow ID> <receipt workflow ID>
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

This is what `just receipt-gaps` printed for the two receipts.
The first line is `just` echoing the command the recipe runs.

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
uv run python scripts/receipt_gaps.py receipt-6e4afdb8-7647-4f9a-b348-15f31de0f68a receipt-cbca96a0-2dee-46a0-83a6-8d58e8f32e35
receipt-6e4afdb8 total 28935ms | WT1 started->completed 28816ms | validate_order: sched->started 4ms started->completed 9ms | compute_total: sched->started 5ms started->completed 9ms | format_receipt: sched->started 9ms started->completed 9ms
receipt-cbca96a0 total 28954ms | WT1 started->completed 28834ms | validate_order: sched->started 12ms started->completed 9ms | compute_total: sched->started 3ms started->completed 12ms | format_receipt: sched->started 4ms started->completed 8ms
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

"WT1" runs from the first `WorkflowTaskStarted` to the first `WorkflowTaskCompleted`.
It spans the timeout and its retry, so WT1 of 28,816 and 28,834 milliseconds is the two Workflow Tasks together.
Each Activity then takes 3 to 12 milliseconds to start and 8 to 12 to finish, so the receipts lost their time before the first `WorkflowTaskCompleted`.
The receipts completed once the final freeze ended.

That is the cross-type damage: a geo bug failed a rollup that has no bug, and held up receipts until the freeze ended.
Now that you have seen a blocking call freeze the loop, the next lesson freezes it with a busy loop.

## Lesson 3: a frozen loop from CPU-bound code

Run `just cpu`.
The `cpu` mode spins in a `while time.monotonic() < deadline` loop with no `await`.
The freeze, the starter's sequencing, and the collateral damage are the same as in Lesson 2.
The CPU reading is the difference.

This `top` row is from the `just cpu` freeze:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2541958 ziggy     25   5 1010032  84248  31716 R  99.0   0.5   0:13.94 python
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The state column reads `R` (running) and `%CPU` reads `99.0`.
The `ps` snapshot from the same moment agrees: the state is `R`, where Lesson 2 showed `S`:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
    PID %CPU STAT     ELAPSED CMD
2541958  6.9 RNl        03:21 /home/ziggy/temporal-async-debug/.venv/bin/python -m temporal_async_debug.worker
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The `6.9` is a lifetime average, diluted by the minutes the Worker spent idle before the run.
This is the shared-GIL case: the busy loop holds the GIL, so the thread never goes idle.
The metrics endpoint still answers, and the slots gauge reads 0 free, as in Lesson 2.

`asyncio ps` has the same shape as Lesson 2: a rollup task parked at `sleep` and a task cut off at `_ActivityWorker._handle_start_activity_task`:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
tid        task id              task name            coroutine stack                                    awaiter chain                                      awaiter name    awaiter id     
2541958    0x7838e6f57f20       Task-241             sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task                                                                    0x0            
2541958    0x7838e6f56f30       Task-260             _ActivityWorker._handle_start_activity_task                                                                           0x0            
2541958    0x7838e56b2e40       Task-261             Worker.poll_activity_task                          _wait -> wait -> _ActivityWorker.run               Task-3          0x7838e7196bd0 
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

`py-spy dump` names the line, and it also shows the CPU case in its thread label.
This is the top of the main thread's dump:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Thread 2541958 (active+gil): "MainThread"
    _apply_mode (temporal_async_debug/activities.py:127)
    get_ip (temporal_async_debug/activities.py:145)
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The line is `activities.py:127`, which is the `while time.monotonic() < deadline` loop.
The label is `active+gil` where the `block` dump said `idle`, so the thread is running and holds the GIL.

The failure is the same as Lesson 2:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
rollup rollup-0b727f37-d63c-40a9-bfb3-79fee4c1f23b FAILED: Activity task timed out
geo geo-a11c48e7-e25f-4d08-8cd1-5d58cd21c209: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
receipt receipt-a9560af2-06be-45ac-940f-565f321bcc55: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
receipt receipt-b43035b5-4630-4478-9c5f-1557d02ee123: OrderReceiptOutput(receipt='order order-1: 59.97 USD')
geo geo-241d5529-8c0f-4b3a-a02b-a12a0cdcf848: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The rollup fails, and both receipts and the bad geo run complete when the freeze ends.

The two freeze lessons differ in one reading:

| | `block` | `cpu` |
|---|---|---|
| CPU (`top`) | `0.0`, state `S` | `99.0`, state `R` |
| `asyncio ps` | one task dead-ended at the SDK handler, the rest parked | same |
| `py-spy dump` | `activities.py:121` (`time.sleep`), thread `idle` | `activities.py:127` (the busy loop), thread `active+gil` |
| Slots gauge | 0 free, 2 used | same |
| Metrics endpoint | reachable | reachable |

Now that you can tell a blocking call from a busy loop, the exercises show how to fix each kind of blocking work.

## Exercises

Each exercise has a `practice` directory with a bug and a `solution` directory with the fix.
You make your changes in `practice`, and each README walks you through the diagnosis, the test, and the fix.

| Directory | Exercise |
|---|---|
| `exercises/01-sync-http-client` | [Fixing a synchronous HTTP client in an async Activity](exercises/01-sync-http-client/README.md) |
| `exercises/02-sleep-between-heartbeats` | [Sleeping between heartbeats in an async Activity](exercises/02-sleep-between-heartbeats/README.md) |
| `exercises/03-cpu-bound` | [Moving CPU-bound work off the event loop](exercises/03-cpu-bound/README.md) |
| `exercises/04-zombie-thread` | [Stopping work that outlives its Activity attempt](exercises/04-zombie-thread/README.md) |
| `exercises/05-catching-blockers-early` | [Catching a short blocking call before it ships](exercises/05-catching-blockers-early/README.md) |
| `exercises/06-finding-the-frozen-worker` | [Finding the frozen Worker in a fleet](exercises/06-finding-the-frozen-worker/README.md) |

Each exercise copy is a flat set of modules plus a `tests/` directory.
It runs from its own directory under the root virtual environment.
The practice edit points carry `TODO PART` comments.

## Recognizing a blocked event loop

A frozen event loop leaves signs you can read before you attach any tool.
Look for these five:

- Workflow Task timeouts on Workflows whose code is fine.
- Workers that stay alive and stay listed as pollers, but stop completing work.
  The process keeps running, and `temporal task-queue describe` still lists the Worker.
- An Activity marked Started long before its code runs.
  The SDK's Rust core takes the task from the server on its own thread, and the loop cannot start your code until it thaws.
- The Worker log line "Task not found when completing".
- The log line `TMPRL1101`, "Potential deadlock detected".
  It depends on timing, so your run may not show it.
  On a Worker with `async def` Activities it can mean the loop froze, not that the Workflow code deadlocked (exercise 02 [captures it](exercises/02-sleep-between-heartbeats/README.md)).

Before you attach any tool, ask the code question: are these Activities `async def`, and what do they call?
A `def` Activity runs on the Worker's `activity_executor`, usually a thread pool, away from the loop.
An `async def` Activity runs on the loop, so a blocking call inside it freezes everything that shares the loop.

The Worker prints "Task not found when completing" when it tries to complete a Workflow Task that the server no longer has, because the task already timed out.
This is the log from the `just block` run of 2026-11-11, with the three matching lines in the order they printed:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
2026-11-11T17:28:06.239953Z  WARN temporalio_sdk_core::worker::workflow: Task not found when completing error=code: 'Some requested entity was not found', message: "Workflow task not found." run_id="01a1cba6-99b2-76a4-9a2f-11048d142686"
2026-11-11T17:28:36.510138Z  WARN temporalio_sdk_core::worker::workflow: Task not found when completing error=code: 'Some requested entity was not found', message: "Workflow task not found." run_id="01a1cba7-1663-73de-8e7f-317b42bc0e2f"
2026-11-11T17:28:36.515420Z  WARN temporalio_sdk_core::worker::workflow: Task not found when completing error=code: 'Some requested entity was not found', message: "Workflow task not found." run_id="01a1cba7-1669-7bbf-90f4-9c05625b729a"
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

This excerpt keeps only the three matching lines and removes the terminal color codes from them; it drops the Worker's other log lines between them.
No number, name, or message inside a quoted line was changed.

The lines arrive when the loop thaws.
In this run the geo Workflow froze the loop twice, once in `get_ip` and once in `get_location`, about 30 seconds apart.
The first line is the rollup's Workflow Task, printed as the first freeze ended.
The other two are the two receipts, printed 5 milliseconds apart at the final thaw, about 40 milliseconds before the geo Workflow's `get_location` Activity completed.
A single line is a reason to check the loop, not a diagnosis.
In the one healthy run captured for this repository (`just healthy` on a fresh server and Worker), the Worker printed none of these lines.

## Observability

The `observability/` directory holds a Prometheus and Grafana stack.
It plots what the Worker and the dev server report, so you can compare a dashboard with the tooling in the lessons.
Grafana corroborates the diagnosis, and the tooling makes it.

Run `just metrics` to start the stack in the background.
It starts Prometheus and Grafana only, with docker-compose v1.
It never starts a Temporal server, because `just server` runs the dev server.
Open the provisioned dashboard at http://localhost:3000.
Grafana allows anonymous viewing, so you need no login.
Run `just metrics-down` to stop the stack.

Prometheus scrapes three endpoints every five seconds.
The Worker exports SDK metrics on port 9464.
The dev server exports server-side metrics on port 9465, and `just server` sets that port with `--metrics-port 9465`.
The failures and backlog panels read the server's metrics, so they need that flag.
The third target, `127.0.0.1:9466`, is for a second Worker, which exercises 03 and 06 start with `ASYNC_DEBUG_METRICS_PORT=9466`.
When no second Worker runs, Prometheus reports that target as down and the dashboard still works.

The dashboard has seven panels.
The seventh, Workflow Task Slots Used Per Worker, draws one line per Worker.
Exercise 06 uses it to tell a frozen Worker from a healthy one.

The captures showed three things about the panels.

First, the latency panels plot milliseconds, because the SDK reports latency in milliseconds.

Second, the Worker's own failure counters stayed empty during a freeze.
A freeze fails no Activity on the Worker side, because the server times the Activity out.
So the failures panel plots the dev server's `activity_timeout` counter by timeout type.

Third, the backlog gauge is nearly flat.
The dev server's `approximate_backlog_age_seconds` for the Activity queue read 0 at the instants sampled during the `cpu` freeze:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
approximate_backlog_age_seconds{namespace="default",namespace_state="active",operation="TaskQueuePartitionManager",partition="0",service_name="matching",task_type="Activity",taskqueue="async_debug_task_queue",worker_version="__unversioned__"} 0
approximate_backlog_age_seconds{namespace="default",namespace_state="active",operation="TaskQueuePartitionManager",partition="1",service_name="matching",task_type="Activity",taskqueue="async_debug_task_queue",worker_version="__unversioned__"} 0
approximate_backlog_age_seconds{namespace="default",namespace_state="active",operation="TaskQueuePartitionManager",partition="2",service_name="matching",task_type="Activity",taskqueue="async_debug_task_queue",worker_version="__unversioned__"} 0
approximate_backlog_age_seconds{namespace="default",namespace_state="active",operation="TaskQueuePartitionManager",partition="3",service_name="matching",task_type="Activity",taskqueue="async_debug_task_queue",worker_version="__unversioned__"} 0
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

`temporal task-queue describe` reported a waiting Activity task over the same freeze.
Treat it as the reliable backlog reading:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
Task Queue Statistics:
    BuildID    TaskQueueType  ApproximateBacklogCount  ApproximateBacklogAge  BacklogIncreaseRate  TasksAddRate  TasksDispatchRate
  UNVERSIONED  workflow                             0  0s                           -6.571412e-06    0.09962184         0.09962841
  UNVERSIONED  activity                             1  4.268144558s                   0.028626636     0.1615123         0.13288566
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Do not read the length of a stall from the latency panels.
In the `just block` run of 2026-11-11, `just receipt-gaps` reported WT1 of 29,002 and 29,001 milliseconds for the two receipts.
The Workflow Task Execution Latency panel drew no line for the receipts in that run.
Its highest reading was about 5.1 seconds, on the `SalesRollupWorkflow` line.
Read the length of a stall from `temporal workflow show` or `just receipt-gaps` instead.

## Platform gotchas

- **Python 3.14 or newer on both sides.**
  The inspector (the Python that runs `python -m asyncio ps`) and the target Worker must both be 3.14 or newer.
  `uv run python -m asyncio ps <PID>` uses the project's 3.14.
- **Linux Yama.**
  The default `kernel.yama.ptrace_scope=1` blocks the inspector from a sibling process.
  Read the current value with `sysctl kernel.yama.ptrace_scope`, which needs no `sudo`.
  Run the inspector with `sudo`, or lower the setting with `sudo sysctl kernel.yama.ptrace_scope=0`.
  That change lasts until the machine restarts.
  `py-spy` needs the same ptrace access.
  The capture machine had `ptrace_scope` at 0 for the lessons, so they quote no refusal.
  The part 1 draft (`docs/drafts/part-1-healthy-worker.md`) quotes both refusals, captured with the value at 1.
- **macOS.**
  Attaching to another process requires `sudo`, for both `asyncio ps` and `py-spy`.
- **Transient failures.**
  Python 3.14's `asyncio ps` can fail on a single call, for example when a task changes while it reads memory.
  Run it again.

## Finding the deliberate bugs

Every deliberately wrong line, setting, or pattern in the root package and in each `practice/` copy carries a marker comment of this exact form, on or immediately above the offending line:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```text
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

Find them all in the root package:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```bash
grep -rn "ANTIPATTERN (deliberate, for teaching)" src
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

That finds two markers: the `time.sleep` call and the CPU-bound loop.
The same search over `exercises/*/practice` finds each exercise's bug.
A `solution/` copy carries no antipattern and no marker, so `grep -rn "ANTIPATTERN (deliberate, for teaching)" exercises/*/solution` returns nothing.
The marker labels the bad pattern for anyone, human or tool, who reads a source file without this README.

## Development

The toolchain is `uv`, `ruff`, `mypy` in strict mode, and `pytest`, run through `just`:

<!-- vale off -->
<!-- vale MasonBase.CodeLineLength = NO -->
```bash
just check            # root gate (ruff check, ruff format --check, mypy strict, pytest), then the solution loop
just check-practice   # ruff and mypy on every exercises/*/practice copy
just fmt              # ruff format and ruff check --fix
just test             # pytest on the root package only
```
<!-- vale MasonBase.CodeLineLength = YES -->
<!-- vale on -->

The root gate excludes `exercises/`.
`just check` then runs each `exercises/*/solution` in its own directory, with ruff, ruff format, mypy, and pytest.
The practice copies get ruff and mypy only, because they carry a bug and an unfinished test.

Tests never need a running Temporal server.
They use the SDK's `ActivityEnvironment` and `WorkflowEnvironment.start_time_skipping()`, and all network calls are mocked.
The live failure signatures in the lessons above are captured by hand, not asserted in CI.

Prose in this repository goes through Vale.
Run `just preflight` once to check the toolchain, `just lint-prose` for style alerts, and `just lint-keyboard` for characters that are not on a keyboard.

## License

MIT.
