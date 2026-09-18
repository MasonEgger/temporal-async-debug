# temporal-async-debug

A deliberately misbehaving Temporal Python demo for learning how to diagnose blocking calls in `async def` Activities.

**Warning: this repository contains deliberately broken code, on purpose, for teaching only.**
**The bugs, the mistuned Worker, and the single-attempt retry policy are all intentional.**
**Do not copy any of it into production.**

## Introduction

A Temporal Python Worker runs its poller, its heartbeat sender, and every `async def` Activity on one asyncio event loop.
One blocking call on that loop freezes them all at once.
That is quick to say and hard to see, so this repository lets you cause it on purpose and then watch it happen from outside the process.

In this tutorial you'll reproduce two production failure modes that look identical to the workflow that suffers them, then tell them apart from tool output alone:

- A frozen event loop, caused by a blocking call (`time.sleep`) inside an async Activity.
- An undersized busy Worker, where a small `max_concurrent_activities` pool fills up and the Worker stops polling for new Activity tasks.

You'll diagnose both with the Python 3.14 native tooling `python -m asyncio ps` and `python -m asyncio pstree`.
These commands read the target process memory without running any code inside it, so they work even while the event loop is fully frozen.
By the end you'll know which signal proves which failure, and why the two need different fixes.

The two Workflows share one Worker:

- `GreetingWorkflow` runs two async Activities (`get_ip` then `get_location`) that you can switch into a blocking or a slow mode.
- `VictimWorkflow` is correct in every respect, the innocent bystander whose work stalls when the misbehaving Activities take over the Worker.

## Prerequisites

To follow along, you'll need:

- **Python 3.14 or newer**, for both the Worker process and the terminal you run `python -m asyncio ps` from.
  The introspection tooling requires 3.14 on both sides.
- **[uv](https://docs.astral.sh/uv/)**, for dependency management.
- **[just](https://github.com/casey/just)**, for the task recipes used throughout.
- **The [Temporal CLI](https://docs.temporal.io/cli)**, which provides the local dev server.
- **`curl`**, for reading the metrics endpoint.

Install the project dependencies once:

```console
uv sync
```

## Step 1: Starting the server and the Worker

You need three terminals.
Each recipe below runs in its own terminal and stays running, so leave each one open.

In terminal one, start the local Temporal dev server:

```console
just server
```

This runs `temporal server start-dev`.
The server exposes its gRPC endpoint on `localhost:7233` and the Temporal Web UI on `http://localhost:8233`.
Leave it running and open the Web UI in a browser; you'll watch the poller list there later.

In terminal two, start the demo Worker:

```console
just worker
```

The Worker connects to the server, registers both Workflows and all three Activities, and prints a startup banner:

```text
========================================================================
temporal-async-debug worker running with PID 12345
Inspect the live event loop from another terminal with either of:
    python -m asyncio ps 12345
    python -m asyncio pstree 12345
Prometheus metrics: http://127.0.0.1:9464/metrics
========================================================================
```

The banner prints the Worker's process ID (`12345` in this example, yours will differ) and the two commands you use to inspect it.
Keep that PID handy.
Every diagnostic command below uses it.

The Worker is deliberately mistuned with `max_concurrent_activities=2`, and its Activities are `async def` with no `activity_executor`, so they run directly on the event loop.
That is what makes both failure modes reproducible.

Now that the server and the Worker are running, you can trigger the first failure.

## Step 2: Reproducing the frozen loop

In terminal three, trigger the frozen-loop lesson:

```console
just block
```

This runs the starter with `--mode block --block-seconds 30 --victims 3`.
It submits one `GreetingWorkflow` whose `get_ip` Activity calls `time.sleep(30)` directly on the event loop, plus three `VictimWorkflow` executions.
For the next 30 seconds the Worker's single event loop is stuck inside that synchronous sleep, so the poller, the heartbeat sender, and every other Activity stop running.
The three victims stall even though their own code is correct, and because heartbeats stop, the misbehaving Activity fails its heartbeat timeout server-side while the process stays frozen.

While the block is in effect, inspect the loop from a fourth terminal (or reuse terminal three once the trigger returns).
Use the PID from the Worker banner:

```console
python -m asyncio ps 12345
```

On a healthy Worker, every task's coroutine stack ends on an asyncio suspension point, a line inside the asyncio library where a coroutine is parked and waiting, such as a sleep timer or a lock acquisition.
That is the shape of a loop that is idle but responsive.

On the blocked Worker, the misbehaving task's stack does not end in the asyncio library.
It ends in this project's own code, at the `time.sleep` call site in `src/temporal_async_debug/activities.py`, inside the `_apply_mode` helper.
A user-code frame at the tail of the stack, sitting on a blocking call, is the frozen-loop signature.

<!-- CAPTURE NEEDED (Mason): paste a real `python -m asyncio ps <PID>` capture here, one healthy and one during the block, taken on a machine with ptrace_scope=0. The build machine ran Linux ptrace_scope=1, which blocks the inspector with "Failed to find the PyRuntime section", so no genuine capture could be recorded. Do not ship invented output. -->

Do not reach for the metrics endpoint to confirm a frozen loop.
Temporal serves its Prometheus endpoint from the SDK's Rust core runtime on its own threads, not from the Python event loop, so the endpoint keeps answering even while the loop is frozen.
In a live block run, every scrape of `http://127.0.0.1:9464/metrics` returned in under a millisecond, the same as when the Worker was healthy.
A responding endpoint does not rule out a frozen loop, so treat the `asyncio ps` stack shape as the definitive call.

Now that you have seen the frozen loop, stop the run (it ends on its own after the block) and reproduce the second failure, which looks the same to a victim but has a different cause.

## Step 3: Reproducing the exhausted slots

In terminal three, trigger the slot-exhaustion lesson:

```console
just slow
```

This runs the starter with `--mode slow --block-seconds 30 --count 2 --victims 3`.
Slow mode awaits `asyncio.sleep(30)` instead of calling `time.sleep`, so the event loop keeps running.
The problem here is capacity, not blocking.
The Worker is mistuned with `max_concurrent_activities=2`, so the two slow Activities take both slots at once and leave nothing for the victims.

Inspect the loop the same way you did in Step 2:

```console
python -m asyncio ps 12345
```

Every task's stack ends on an asyncio suspension point, including the two slow Activities parked on `asyncio.sleep`.
The loop is healthy and nothing is blocked.
That healthy stack shape is the first thing that separates this failure from the frozen loop.

Since the loop is fine, the evidence is in the metrics.
Read the Activity slot gauge that the SDK's Rust core exports:

```console
curl -s http://127.0.0.1:9464/metrics | grep 'temporal_worker_task_slots_available.*ActivityWorker'
```

On a healthy Worker, the Activity slot pool reports its full size:

```text
temporal_worker_task_slots_available{namespace="default",service_name="temporal-core-sdk",task_queue="async-debug-task-queue",worker_type="ActivityWorker"} 2
```

While both slow Activities hold their slots, the same gauge reads `0`:

```text
temporal_worker_task_slots_available{namespace="default",service_name="temporal-core-sdk",task_queue="async-debug-task-queue",worker_type="ActivityWorker"} 0
```

A value of `0` means the Worker has no free Activity slots, so it stops polling the Task Queue for new Activity tasks.
Schedule-to-start latency then climbs for every other Workflow on the queue, including the innocent victims, which you can watch on the `temporal_activity_schedule_to_start_latency` histogram.
In the Temporal Web UI at `http://localhost:8233`, the Worker disappears from the Task Queue's poller list even though the process is alive and healthy, because it is no longer polling.

One timing detail matters for what you will actually observe.
The slow Activity heartbeats once and then awaits for 30 seconds, but `GreetingWorkflow` sets a 10 second `heartbeat_timeout` with `maximum_attempts=1`.
Because slow mode is cooperative, the server cancels each slow Activity about 10 seconds in, when its heartbeat times out, and both slots free up then rather than at the full 30 seconds.
So the exhaustion window you can catch with `curl` is roughly the first 10 to 14 seconds after `just slow`, not the whole block duration.

Now that you have both failures on record, you can compare their signatures side by side.

## Telling the two apart

Both failures look the same to a victim Workflow: its work stalls.
The tooling tells them apart.

- **Frozen loop** (Step 2, `just block`): a task stack ends in user code at the `time.sleep` call site.
  This is the definitive signal, because the metrics endpoint keeps responding off the event loop and cannot confirm the freeze.
- **Busy Worker** (Step 3, `just slow`): every task stack ends on an asyncio suspension point, `temporal_worker_task_slots_available` reads `0`, `temporal_activity_schedule_to_start_latency` climbs, and the Worker drops off the poller list in the Web UI.

The fixes differ too.
You fix a frozen loop by not blocking the loop: await `asyncio.sleep` for a cooperative delay, or move truly blocking work into an executor.
You fix a busy Worker by sizing `max_concurrent_activities` to the concurrency and load you expect.

## Platform gotchas

- Both the inspector (`python -m asyncio ps`) and the target Worker must run Python 3.14 or newer.
- On Linux, the default Yama setting `ptrace_scope=1` blocks the inspector and presents as `Failed to find the PyRuntime section`. Fix it by running the inspector under `sudo`, or set `ptrace_scope=0` for the session with `sudo sysctl kernel.yama.ptrace_scope=0`.
- On macOS, `python -m asyncio ps` requires `sudo`.
- On Python 3.14, `asyncio ps` can fail transiently while it reads a moving target, so re-run the command if it errors out once.

## The antipattern markers

Every deliberately wrong line in this repository carries a fixed, greppable comment, so no one mistakes a teaching bug for a pattern to copy:

```text
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```

List every intentional bug, mistuning, and disabled safety at once:

```console
grep -rn "ANTIPATTERN (deliberate, for teaching)" src/
```

That command surfaces the `time.sleep` call, the `maximum_attempts=1` retry policy, the victim's `schedule_to_start_timeout`, and the `max_concurrent_activities=2` mistuning.

## What you learned

You reproduced two failures that stall innocent Workflows in the same way, and you separated them from outside the process.
A frozen loop shows a user-code frame at the tail of a task stack in `asyncio ps`, and the metrics endpoint cannot confirm it because that endpoint runs off the loop.
An exhausted Worker shows healthy stacks, a `temporal_worker_task_slots_available` reading of `0`, and climbing schedule-to-start latency.
The first needs a non-blocking Activity, the second needs a larger slot pool.

## Tutorial

A full walkthrough of the mechanism lives on masonegger.com.

TODO: link the published tutorial on masonegger.com once it is live.

## License

[MIT](LICENSE), copyright 2026 Mason Egger.
