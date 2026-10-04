# temporal-async-debug

A Temporal Python demo that breaks on purpose, so you can practice diagnosing why a Worker stops doing work.

**Warning: this repository contains deliberately broken code, written for educational purposes only.**
**Every bug and mistuning here is a feature of the demo.**
**Do not copy any of it into a real codebase.**

This repository is the companion to a tutorial on diagnosing blocking and saturation failures in `async def` Activities.
It runs four unrelated Workflow types on one Worker, then drives one of them into a range of failure modes.
You reproduce each failure and diagnose it from outside the process, with Python 3.14 native tooling (`python -m asyncio ps` and `pstree`), `py-spy dump`, the `temporal` command-line tool, and the Temporal SDK's Prometheus metrics.
The code carries no instrumentation for the diagnosis.

Tutorial: TODO (link to the masonegger.com tutorial and deep-dive post once published).

## The headline: one Workflow type takes down another

The four Workflow types have nothing to do with each other:

- `GeoEnrichmentWorkflow` looks up an IP address and its location over HTTP.
- `OrderReceiptWorkflow` builds a receipt in memory, instantly.
- `SalesRollupWorkflow` sums four figures after a two-second cooperative pause.
- `PriceQuoteWorkflow` computes a quote in memory and is the one sample that sets a `schedule_to_start_timeout`.

They share one Worker, and the Python Worker runs its pollers, its heartbeat sender, Workflow Task processing, and every `async def` Activity on a single asyncio event loop.
So when one geo Activity misbehaves, the rollups, receipts, and quotes fail too, even though their code is correct.
Nothing in their code or their Event History names the cause.
You find it with the tooling in the lessons below.

The two root causes look the same from a Workflow's point of view and are different in the tools:

- A frozen event loop: something blocks or burns CPU on the loop and nothing else on the Worker can run.
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

- CPU separates the two freeze causes: near zero for a blocking call (`time.sleep` releases the Global Interpreter Lock, or GIL), 100 percent for CPU-bound code (the loop holds the GIL).
- A saturated Worker looks different.
  Every task sits at a healthy await, `temporal_worker_task_slots_available` reads 0, and the backlog age in `temporal task-queue describe` keeps climbing.

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
This is the banner from the capture session (your PID will differ):

```text
========================================================================
temporal-async-debug worker running with PID 2379759
Inspect the live event loop from another terminal with either of:
    python -m asyncio ps 2379759
    python -m asyncio pstree 2379759
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
| `just healthy` | Full fleet (geo, rollup, receipt, quote), all completing |
| `just trigger` | Smaller healthy fleet (geo and receipts only), a quick smoke test |
| `just block [seconds]` | A geo run calls `time.sleep` and freezes the loop (default 30) |
| `just cpu [seconds]` | A geo run spins in a busy loop and freezes the loop (default 30) |
| `just slow [seconds]` | Two geo runs hold both Activity slots with `asyncio.sleep` (default 30) |
| `just slow-heartbeat [seconds]` | Two geo runs hold both slots, but heartbeat correctly (default 30) |
| `just stuck [seconds]` | A geo run waits without heartbeating and trips its heartbeat timeout (default 30) |

The Temporal Web UI is at http://localhost:8233.
Each geo run has two Activities (`get_ip`, then `get_location`), and both apply the delay, so a 30-second scenario holds for about 60 seconds.

### About the captured output

Everything quoted in the lessons is real output, captured against `temporal server start-dev` (Temporal CLI 1.6.2, server 1.30.2) with `temporalio` 1.33.0 on Python 3.14.3, Linux.
Two edits were made for readability: runs of spaces in `asyncio ps` tables were collapsed, and the long absolute paths in `pstree` were trimmed to file names.
The `py-spy dump` output is unedited apart from the omitted trailing thread rows noted in each lesson.
Rows that are identical in every capture (housekeeping tasks owned by the SDK's `Worker.run`) are omitted from some `ps` excerpts.
Task numbers, addresses, and PIDs differ on every run, and the captures came from several Worker runs.

## Lesson 1: a healthy Worker

Run `just healthy`.
Every run completes:

```text
geo geo-33aedd13-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-1794e912-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
receipt receipt-f79e2387-...: OrderReceiptOutput(receipt='order order-0: 59.97 USD')
rollup rollup-01151c17-...: SalesRollupOutput(summary='Sales rollup for 2026-01: total 6030')
quote quote-ae23b0b3-...: PriceQuoteOutput(quote='Quote for 1 x SKU-0: 9.99 USD')
```

An idle Worker's `python -m asyncio ps <PID>` shows every task parked on an asyncio suspension point.
This excerpt keeps the poller row:

```text
tid      task id         task name  coroutine stack                                  awaiter chain                  awaiter name  awaiter id
2379759  0x78f59d6cb200  Task-116   Worker.poll_activity_task                         _wait -> wait -> _ActivityWorker.run  Task-3  0x78f59f2aea00
```

The matching `pstree` branch ends in `Worker.poll_activity_task`, which is the Worker waiting on the Temporal server for its next Activity:

```text
└── (T) Task-116
    └──  Worker.poll_activity_task worker.py:226
```

The healthy readings to remember:

- CPU: low (`ps -o %cpu,comm -p <PID>` printed `6.3 python3`, a lifetime average that includes startup).
- Slots: `temporal_worker_task_slots_available` for `worker_type="ActivityWorker"` reads 2 (the Worker is sized with `max_concurrent_activities=2`).
- Latency: `temporal_activity_schedule_to_start_latency` has a small sum and count (1227 and 15 at capture time, in milliseconds).

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 2
temporal_activity_schedule_to_start_latency_sum{...} 1227
temporal_activity_schedule_to_start_latency_count{...} 15
```

No timeout fires.

## Lesson 2: a frozen loop from a blocking call

Run `just block`.
In `activities.py`, the `block` mode calls `time.sleep` inside an `async def`.
The line looks harmless, and it carries the antipattern marker (see [Finding the deliberate bugs](#finding-the-deliberate-bugs)).

While the freeze is active, run the introspection commands from a second terminal.
`asyncio ps` and `py-spy` both work because they read process memory without running code in it.

The metrics scrape stays fast.
The SDK's Rust core serves the endpoint off the event loop, so a reachable endpoint tells you nothing about the loop.
One `curl` during the freeze took 11 ms.
Do not use it as the frozen-loop signal.

The CPU is near zero, because `time.sleep` releases the GIL and the process is idle inside a system call (`top` reported `0.0` in state `S`).
Both Activity slots are in use:

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
```

The first tool is `python -m asyncio ps <PID>`.
This is what it printed during a freeze (rows for the SDK's housekeeping tasks are trimmed):

```text
tid      task id         task name  coroutine stack                                                                                                                   awaiter chain  awaiter name  awaiter id
3125455  0x752bb3470ad0  Task-6     Queue.get -> _ActivityWorker.run.<locals>.raise_from_exception_queue  _wait -> wait -> _ActivityWorker.run  Task-3  0x752bb33aaa00
3125455  0x752bb31682f0  Task-20    sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
3125455  0x752bb3146650  Task-27    BoundedVisitorFunctions._drain_tasks -> BoundedVisitorFunctions.drain -> PayloadVisitor.visit -> decode_activation -> _WorkflowWorker._handle_activation  0x0
3125455  0x752bb16218b0  Task-29    _ActivityWorker._handle_start_activity_task  0x0
3125455  0x752bb16224e0  Task-30    Worker.poll_activity_task  _wait -> wait -> _ActivityWorker.run  Task-3  0x752bb33aaa00
```

Here is how to read it:

- Task-29 is the wedged task.
  Its stack stops at the SDK frame `_ActivityWorker._handle_start_activity_task`, with no suspension point beneath it.
  A task that is parked always ends on an await such as `sleep`, `wait`, or `Queue.get`, and this one does not.
- Task-20 is a `roll_up_sales` Activity parked on `sleep`.
  Its timer is a two-second sleep, and on a frozen loop that timer cannot fire.
- Task-6, Task-27, and Task-30 are parked at real awaits, but the loop that would wake them is stuck.

The `pstree` view shows the same thing as branches:

```text
└── (T) Task-20
    └──  _ActivityWorker._handle_start_activity_task _activity.py:351
        └──  _ActivityWorker._execute_activity _activity.py:681
            └──  _ActivityInboundImpl.execute_activity _activity.py:889
                └──  roll_up_sales rollup.py:43
                    └──  sleep tasks.py:702
└── (T) Task-29
    └──  _ActivityWorker._handle_start_activity_task _activity.py:351
```

Task-20 ends on `sleep`.
Task-29 ends on the SDK handler and nothing else.
That is the frozen-loop shape.

It does not name the file.
No frame in Task-29 points at `activities.py`.
That is the limit described in [the diagnostic story](#the-diagnostic-story-two-tools-for-a-frozen-loop): the blocking call is synchronous, so it is not on the asyncio stack.

The second tool is `py-spy dump --pid <PID>`, which reads the OS thread stack.
Run it with `uvx py-spy dump --pid <PID>`, using the Worker's own Python PID (the `.venv` `python3`, not the `uv` wrapper process).
This is the real dump from the same freeze:

```text
Process 3125455: /home/ziggy/temporal-async-debug/.venv/bin/python3 -m temporal_async_debug.worker
Python v3.14.3 (/home/ziggy/.local/share/uv/python/cpython-3.14.3-linux-x86_64-gnu/bin/python3.14)

Thread 3125455 (idle): "MainThread"
    _apply_mode (temporal_async_debug/activities.py:118)
    get_ip (temporal_async_debug/activities.py:158)
    execute_activity (temporalio/worker/_activity.py:889)
    _execute_activity (temporalio/worker/_activity.py:681)
    _handle_start_activity_task (temporalio/worker/_activity.py:351)
    _run (asyncio/events.py:94)
    _run_once (asyncio/base_events.py:2046)
    run_forever (asyncio/base_events.py:677)
    run_until_complete (asyncio/base_events.py:706)
    run (asyncio/runners.py:127)
    run (asyncio/runners.py:204)
    <module> (temporal_async_debug/worker.py:107)
    _run_code (<frozen runpy>:88)
    _run_module_as_main (<frozen runpy>:199)
```

The top frame is `_apply_mode` at `activities.py:118`, which is the `time.sleep` call.
The frames below it are the same SDK chain that `asyncio ps` stopped at (`_handle_start_activity_task`, `_activity.py:351`), now continued down into your code.
The `idle` label means the thread is not holding the GIL, which matches the near-zero CPU.
The dump also lists two idle pool threads (`temporal_workflow__0` and `asyncio_0`), which are omitted here.

The server's view of the Worker changes too.
A frozen Worker stops polling, so its poller `LastAccessTime` in `temporal task-queue describe --task-queue async-debug-task-queue` goes stale instead of refreshing.
This is the output during a freeze:

```text
Pollers:
    BuildID    TaskQueueType   Identity    LastAccessTime  RatePerSecond
  UNVERSIONED  workflow       3125455@host  39 seconds ago         100000
  UNVERSIONED  activity       3125455@host  38 seconds ago         100000
```

Read this one with care.
An idle, healthy Worker printed the same 38 and 39 seconds in its own capture, because its long poll only refreshes every so often.
A single reading cannot tell the two apart.
The signal is the age growing across repeated readings instead of resetting, until the poller eventually drops off the list.
The poller does not vanish the moment the loop freezes, and this README did not capture the moment it drops off.

Together the tools give the full answer.
`asyncio ps` says the loop is frozen and which task is wedged.
`py-spy` says the line.
The CPU reading then separates this case from the next one.

What fails.
The rollup Activity was in flight when the freeze landed, so its Workflow fails:

```text
rollup rollup-7ad72ae7-...: FAILED: Activity task timed out
```

The starter's message does not say which timeout fired.
`temporal workflow show --workflow-id <id>` does:

```text
Failure
    Message: Activity task timed out
    Cause:
        Message: activity ScheduleToClose timeout
        Cause:
            Message: activity StartToClose timeout
```

The cause chain says the last attempt tripped `start_to_close` (10 seconds) and the call then hit `schedule_to_close` (20 seconds).
That fits the default retry policy starting a second attempt, which could not run on the frozen loop.
The History also shows a `WorkflowTaskTimedOut` event, because a frozen loop stops Workflow Task processing too.

The geo Activities that were already running at the freeze completed, because the geo Workflow gives each Activity a generous 120-second `start_to_close`.
That is the cross-type damage: a geo bug failed a rollup that has no bug.

## Lesson 3: a frozen loop from CPU-bound code

Run `just cpu`.
The `cpu` mode spins in a `while time.monotonic() < deadline` loop with no `await`.
The freeze and the collateral damage are the same as in Lesson 2.
The CPU reading is the difference:

```text
    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
2379759 ziggy     25   5  878992  88268  32020 R 100.0   0.5   0:05.97 python3
```

The state is `R`, and the process sat between 80 and 100 percent in every one of 24 samples taken while the freeze was active.
This is the literal shared-GIL case.
The metrics endpoint still answers, and the slots still read 0:

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
```

`asyncio ps` has the same shape as Lesson 2: a stale `sleep -> roll_up_sales` row and a running task cut off at `_ActivityWorker._handle_start_activity_task`:

```text
2379759  0x78f59c428140  Task-247  sleep -> roll_up_sales -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
2379759  0x78f59d5cd8b0  Task-264  _ActivityWorker._handle_start_activity_task  0x0
```

`py-spy dump` names the line, and it also shows the CPU case in its thread label.
This is the top of the main thread's dump during a `just cpu` freeze:

```text
Thread 3191020 (active+gil): "MainThread"
    _apply_mode (temporal_async_debug/activities.py:124)
    get_ip (temporal_async_debug/activities.py:158)
    execute_activity (temporalio/worker/_activity.py:889)
    _execute_activity (temporalio/worker/_activity.py:681)
    _handle_start_activity_task (temporalio/worker/_activity.py:351)
```

The line is `activities.py:124`, which is the `while time.monotonic() < deadline` loop.
The label is `active+gil` where the `block` dump said `idle`, so the thread is running and holds the GIL.

The failure is the same: the rollup run ends with `Activity task timed out`.

The two freeze lessons differ in one reading:

| | `block` | `cpu` |
|---|---|---|
| CPU | about 0 percent, state `S` | 80 to 100 percent, state `R` |
| `asyncio ps` | stale parked tasks plus one task dead-ended at the SDK handler | same |
| `py-spy dump` | `activities.py:118` (`time.sleep`), thread `idle` | `activities.py:124` (the busy loop), thread `active+gil` |
| Metrics endpoint | reachable | reachable |

## Lesson 4: slot exhaustion

Run `just slow`.
Two geo runs await `asyncio.sleep(30)` in each Activity, holding both slots.
The loop is healthy the whole time.
The starter submits the hoggers first, waits until the slots gauge reads 0, and then submits a rollup, two receipts, and a quote.

CPU is near zero (`top` reported `0.0`).
The slots gauge reads 0:

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
```

`asyncio ps` looks healthy.
Both hogging Activities are parked on `sleep`, a suspension point, and the full call chain is visible down to your code:

```text
2379759  0x78f59d5ce120  Task-347  sleep -> _apply_mode -> get_ip -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
2379759  0x78f59c467980  Task-349  sleep -> _apply_mode -> get_ip -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
2379759  0x78f59c467b60  Task-350  Worker.poll_activity_task  _wait -> wait -> _ActivityWorker.run  Task-3  0x78f59f2aea00
```

This is the contrast with Lessons 2 and 3.
Here the stacks are complete and end on `sleep`, and the poller task is still parked normally.

The Worker also stops polling for new Activity tasks while every slot is full.
Work queues on the server instead.
`temporal task-queue describe --task-queue async-debug-task-queue` showed the backlog during a 12-second variant (`just slow 12`):

```text
Task Queue Statistics:
    BuildID    TaskQueueType  ApproximateBacklogCount  ApproximateBacklogAge  BacklogIncreaseRate  TasksAddRate  TasksDispatchRate
  UNVERSIONED  workflow                             0  0s                          -0.0002169013    0.18833295         0.18854985
  UNVERSIONED  activity                             4  7.334416053s                   0.12593038     0.1887267         0.06279631
```

Four Activity tasks were waiting, the oldest for 7.3 seconds.
In another capture (`just slow-heartbeat`) the backlog count was 1 with an age of 13.4 seconds:

```text
  UNVERSIONED  activity                             1  13.4003485s                     0.09423415    0.15683448         0.06260033
```

The backlog age is the live saturation tell.
It climbs for as long as every slot stays full.

The Worker's poller `LastAccessTime` goes stale too, because the Worker stops polling for Activities while its slots are full.
That reading is coarse, for the reason given in Lesson 2: a single value is ambiguous, and the signal is the age growing across readings.
In that same `slow-heartbeat` capture the poller rows read "13 seconds ago", which is fresher than the freeze reading, so the age depends on when the Worker last finished a poll.
Use the backlog age and the slots gauge first, and treat the poller age as supporting evidence.

What fails.
The starved bystanders fail with a schedule-to-start style timeout:

```text
receipt receipt-f060db0b-...: FAILED: Activity task timed out
receipt receipt-0a100960-...: FAILED: Activity task timed out
rollup rollup-efa247b3-...: FAILED: Activity task timed out
quote quote-6eebe785-...: FAILED: Activity task timed out
```

`temporal workflow show` gives the cause for each of them:

```text
Failure
    Message: Activity task timed out
    Cause:
        Message: activity ScheduleToStart timeout
```

The receipts failed 10 seconds after submission, the quote after 5, and the rollup after 20, which matches their configured budgets.
The receipt and rollup Workflows set only `schedule_to_close`, and the server still labeled the failure `ScheduleToStart`, because the Activity never started.
Read the label as "never got a slot".

The latency histogram is subtle.
`temporal_activity_schedule_to_start_latency` is recorded when a queued task finally starts.
A task that times out in the queue never records a value.
Over the full 30-second `slow` run the sum moved only from 1569 to 1574 milliseconds:

```text
temporal_activity_schedule_to_start_latency_sum{...} 1569
temporal_activity_schedule_to_start_latency_count{...} 37
```

When the jam is short enough that queued work eventually starts, the metric shows the wait.
In the 12-second run, the sum went from 1620 to 15779 milliseconds as the queued tasks started late (count 48 to 51).
Read the backlog age first, because it is live.
The latency metric confirms the saturation afterward.

The fix is different from Lessons 2 and 3.
Do not touch the event loop.
Size the Worker for the load (raise `max_concurrent_activities`, add Workers) or move long work off this queue.

## Lesson 5: a correct long-running Activity (slow_heartbeat)

Run `just slow-heartbeat`.
The `slow_heartbeat` mode is the right way to hold a slot for legitimately long work.
It awaits `asyncio.sleep` in 3-second steps and calls `activity.heartbeat` between steps, and the Workflow sets a 10-second `heartbeat_timeout` that each heartbeat satisfies.
This is the one mode with no antipattern marker.

The tool output looks like Lesson 4:

- `asyncio ps` shows both Activities parked on `sleep -> _apply_mode -> get_ip -> ...`.
- CPU is near zero.
- The slots gauge reads 0 and `temporal_worker_task_slots_used` for the ActivityWorker reads 2:

```text
temporal_worker_task_slots_available{...,worker_type="ActivityWorker"} 0
temporal_worker_task_slots_used{...,worker_type="ActivityWorker"} 2
```

Both geo runs complete, and the bystanders still starve:

```text
receipt receipt-43d97de3-...: FAILED: Activity task timed out
receipt receipt-694557cd-...: FAILED: Activity task timed out
rollup rollup-dac6654c-...: FAILED: Activity task timed out
geo geo-a114b145-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
geo geo-c3a22bc7-...: GeoEnrichmentOutput(ip='256.256.256.256', location='Milky Way Galaxy')
```

The lesson: correct code on an undersized Worker still starves other work.
No heartbeat timeout fires here.
The fix is the Worker's size, not the Activity.

## Lesson 6: a heartbeat timeout (stuck_no_heartbeat)

Run `just stuck`.
The `stuck_no_heartbeat` mode awaits one long `asyncio.sleep` and never heartbeats, while the Workflow sets the same 10-second `heartbeat_timeout` as Lesson 5.
The loop is healthy, and `asyncio ps` shows a parked Activity:

```text
2379759  0x78f59d5ebd40  Task-499  sleep -> _apply_mode -> get_ip -> _ActivityInboundImpl.execute_activity -> _ActivityWorker._execute_activity -> _ActivityWorker._handle_start_activity_task  0x0
```

One slot is in use (the gauge read 1 with a healthy geo run alongside).
The run fails 10 seconds in, not 30:

```text
geo geo-d61e8c09-...: FAILED: Activity task timed out
```

```text
Failure
    Message: Activity task timed out
    Cause:
        Message: activity Heartbeat timeout
```

The healthy geo run alongside it completes.
The `heartbeat_timeout` turned a silent hang into a fast, named failure, which is why long Activities should heartbeat and set one.

## Lesson 7: the schedule-to-start sample

`PriceQuoteWorkflow` is the one place `schedule_to_start_timeout` is set (5 seconds, marked as an antipattern in `quote.py`), because a stale price quote is worthless.
You do not run a separate recipe.
The quote rides along in `just slow` and `just slow-heartbeat` (the `healthy` recipe runs it too, where it finishes instantly).

With every slot held, the quote cannot start, and it fails first, after 5 seconds, before the receipts (10) and the rollup (20):

```text
quote quote-6eebe785-...: FAILED: Activity task timed out
```

```text
Failure
    Message: Activity task timed out
    Cause:
        Message: activity ScheduleToStart timeout
```

This is the one timeout that is a direct statement about the Worker, not about the Activity.
The Activity ran for zero seconds.
It fails fast and visibly when the Worker falls behind, and that is the rare case where you would want that.

## Which timeout fires, and how to tell

| Mode (recipe) | Family | What fails | Timeout in the failure | CPU | `asyncio ps` | `py-spy dump` | Slots gauge |
|---|---|---|---|---|---|---|---|
| healthy | none | nothing | none | low | all parked | idle pool threads only | 2 free |
| `block` | frozen loop | in-flight rollup | `ScheduleToClose` caused by `StartToClose` | about 0 | one task dead-ended at the SDK handler, the rest parked | `time.sleep` line, thread `idle` | 0 |
| `cpu` | frozen loop | in-flight rollup | same as `block` | 80 to 100 percent | same as `block` | busy-loop line, thread `active+gil` | 0 |
| `slow` | saturated Worker | rollup, receipts, quote | `ScheduleToStart` | about 0 | every task parked, stacks end on `sleep` | not needed | 0 |
| `slow_heartbeat` | saturated Worker | rollup, receipts | `ScheduleToStart` | about 0 | every task parked, stacks end on `sleep` | not needed | 0 |
| `stuck_no_heartbeat` | heartbeat loss | the geo run itself | `Heartbeat` | about 0 | parked, stack ends on `sleep` | not needed | 1 free |
| quote sample | saturated Worker | quote first | `ScheduleToStart` (5 s) | about 0 | every task parked | not needed | 0 |

The split to remember:

- Frozen loop (`block`, `cpu`): the metrics endpoint answers anyway, so it cannot help.
  The tell is the `asyncio ps` shape (one task dead-ended at `_ActivityWorker._handle_start_activity_task`, the rest parked at awaits) and the CPU reading (about 0 for `block`, 100 percent for `cpu`).
  `py-spy dump` then names the exact line in `activities.py`.
- Saturated Worker (`slow`, `slow_heartbeat`): the loop is healthy.
  Every task is parked at a healthy await and none is dead-ended, slots read 0, and the task queue shows a backlog whose age keeps climbing.
  The poller `LastAccessTime` goes stale, and the schedule-to-start latency histogram records the wait only once queued work finally starts.

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
A Workflow's business logic depends on whether it is correct, not on how long it takes, and a Workflow timeout would end a Workflow that would have recovered.
The Activity timeouts are where the symptoms show up.

Two of the timeouts are tuned for the demo and should not be copied:

- The geo Activities use a generous 120-second `start_to_close` so that `slow` and `slow_heartbeat` hold their slots for the whole delay.
- The retry policy uses `maximum_attempts=1`, so the first failure surfaces instead of being retried and hidden.

## Platform gotchas

- **Python 3.14 or newer on both sides.**
  The inspector (the Python that runs `python -m asyncio ps`) and the target Worker must both be 3.14 or newer.
  `uv run python -m asyncio ps <PID>` uses the project's 3.14.
- **Linux Yama.**
  The default `kernel.yama.ptrace_scope=1` blocks the inspector from a sibling process.
  For `asyncio ps` the failure message is `Failed to find the PyRuntime section`.
  Run the command with `sudo`, or lower the setting with `sudo sysctl kernel.yama.ptrace_scope=0`.
  `py-spy` needs the same ptrace access, and without it `py-spy dump` printed `Permission Denied: Try running again with elevated permissions` on the capture machine before `ptrace_scope` was lowered.
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

That covers `time.sleep`, the CPU-bound loop, `stuck_no_heartbeat`, the quote's `schedule_to_start_timeout`, `max_concurrent_activities=2`, and `maximum_attempts=1`.
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
