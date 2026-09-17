# temporal-async-debug

A deliberately misbehaving Temporal Python demo for learning how to diagnose blocking calls in `async def` Activities.

**Warning: this repository contains deliberately broken code, on purpose, for teaching only.**
**The bugs, the mistuned Worker, and the single-attempt retry policy are all intentional.**
**Do not copy any of it into production.**

## What this repository demonstrates

A Temporal Python Worker runs its poller, its heartbeat sender, and every `async def` Activity on one asyncio event loop.
One blocking call on that loop freezes them all at once.

This demo reproduces two production failure modes that look identical from the outside and have different fixes:

- A frozen event loop, caused by a blocking call (`time.sleep`) inside an async Activity.
- An undersized busy Worker, where a small `max_concurrent_activities` slot pool fills up and the Worker stops polling for new Activity tasks.

You reproduce each failure, then diagnose it from outside the process with the Python 3.14 native tooling `python -m asyncio ps` and `python -m asyncio pstree`.
These commands read the target process memory without executing any code inside it, so they work even while the event loop is fully frozen.

The two Workflows share one Worker:

- `GreetingWorkflow` runs two async Activities (`get_ip` then `get_location`) that you can switch into a blocking or a slow mode.
- `VictimWorkflow` is correct code in every respect, the innocent bystander whose work stalls when the misbehaving Activities take over the Worker.

## Requirements

- Python 3.14 or newer for both the Worker process and the terminal you run `python -m asyncio ps` from, because the introspection tooling requires 3.14 on both sides.
- [uv](https://docs.astral.sh/uv/) for dependency management.
- [just](https://github.com/casey/just) for the task recipes below.
- The [Temporal CLI](https://docs.temporal.io/cli), which provides the local dev server.
- `curl` for reading the metrics endpoint.

Install the project dependencies once with `uv sync`.

## Quickstart

You need three terminals.
Each recipe runs in its own terminal and stays running.

In terminal one, start the local Temporal dev server:

```console
just server
```

This runs `temporal server start-dev`.
The server exposes its gRPC endpoint on `localhost:7233` and the Temporal Web UI on `http://localhost:8233`.

In terminal two, start the demo Worker:

```console
just worker
```

The Worker prints a startup banner with its process ID and the two commands you use to inspect it:

```text
========================================================================
temporal-async-debug worker running with PID 12345
Inspect the live event loop from another terminal with either of:
    python -m asyncio ps 12345
    python -m asyncio pstree 12345
Prometheus metrics: http://127.0.0.1:9464/metrics
========================================================================
```

Keep that PID handy.
Every diagnostic command in the lessons below uses it.

In terminal three, trigger one of the two lessons.
Run `just block` for the frozen-loop lesson or `just slow` for the slot-exhaustion lesson:

```console
just block
```

`just block` runs the starter with `--mode block --block-seconds 30 --victims 3`.
`just slow` runs it with `--mode slow --block-seconds 30 --count 2 --victims 3`.
For a healthy baseline run with no delay, use `just trigger`.

## Lesson 1: the frozen loop

Run `just block` in terminal three while the Worker runs in terminal two.

This submits a `GreetingWorkflow` whose `get_ip` Activity calls `time.sleep(30)` on the event loop, plus three `VictimWorkflow` executions.
For the next 30 seconds the Worker's single event loop is stuck inside that synchronous sleep, so the poller, the heartbeat sender, and every other Activity stop running.
The three victims stall even though their own code is correct.

While the block is in effect, inspect the loop from a fourth terminal (or reuse terminal three once the trigger returns):

```console
python -m asyncio ps 12345
```

On a healthy Worker, every task's coroutine stack ends on an asyncio suspension point, a line inside the asyncio library where a coroutine is parked waiting, such as a sleep timer or a lock acquisition.
That is the signature of a loop that is idle but responsive.

On the blocked Worker, the misbehaving task's stack does not end in the asyncio library.
It ends in this project's own code, at the `time.sleep` call site in `src/temporal_async_debug/activities.py` inside the `_apply_mode` helper.
A user-code frame at the tail of the stack, sitting on a blocking call, is the frozen-loop signature.

The metrics endpoint can offer a weaker, secondary hint, but treat the stack shape as the definitive call.
Temporal's Prometheus endpoint is served by the SDK's Rust core runtime on its own threads, not by the Python event loop, so it can keep answering even while the loop is frozen.
The `curl http://127.0.0.1:9464/metrics` request may stall in some cases, but an endpoint that still responds does not rule out a frozen loop, so do not lean on it.

## Lesson 2: the exhausted slots

Run `just slow` in terminal three.

This submits two `GreetingWorkflow` executions in `slow` mode plus three victims.
Slow mode awaits `asyncio.sleep(30)` instead of calling `time.sleep`, so the event loop keeps running.
The problem is capacity, not blocking.
The Worker is deliberately mistuned with `max_concurrent_activities=2`, so the two slow Activities hold both slots for the full 30 seconds and no slot is free for anything else.

Inspect the loop the same way:

```console
python -m asyncio ps 12345
```

Every task's stack ends on an asyncio suspension point, including the two slow Activities parked on `asyncio.sleep`.
The loop is healthy and nothing is blocked.
This is the first thing that distinguishes Lesson 2 from Lesson 1.

Now read the slot metrics the SDK's Rust core exports:

```console
curl http://127.0.0.1:9464/metrics | grep temporal_worker_task_slots_available
```

`temporal_worker_task_slots_available` reads 0 for the Activity slot pool while both slots are held.
With no free slots the Worker stops polling the Task Queue for new Activity tasks, so schedule-to-start latency climbs for every other Workflow on the queue, including the innocent victims.
In the Temporal Web UI at `http://localhost:8233`, the Worker disappears from the Task Queue's poller list even though the process is alive and healthy, because it is no longer polling.

## Telling the two apart

Both failures look the same to a victim Workflow: its work stalls.
The tooling tells them apart.

- Frozen loop (Lesson 1, `just block`): a task stack ends in user code at the `time.sleep` call site, which is the definitive signal because the metrics endpoint can keep responding off the event loop.
- Busy Worker (Lesson 2, `just slow`): every task stack ends on an asyncio suspension point, `temporal_worker_task_slots_available` reads 0, schedule-to-start latency climbs, and the Worker drops off the poller list in the Web UI.

The fixes differ too.
A frozen loop is fixed by not blocking the loop: await `asyncio.sleep` for a cooperative delay, or move truly blocking work into an executor.
A busy Worker is fixed by sizing `max_concurrent_activities` to the expected concurrency and load.

## Platform gotchas

- Both the inspector (`python -m asyncio ps`) and the target Worker must run Python 3.14 or newer.
- On Linux, the default Yama setting `ptrace_scope=1` blocks the inspector and presents as `Failed to find the PyRuntime section`; fix it by running the inspector under `sudo`, or set `ptrace_scope=0` with `sudo sysctl kernel.yama.ptrace_scope=0` for the session.
- On macOS, `python -m asyncio ps` requires `sudo`.
- On Python 3.14, `asyncio ps` can fail transiently while it reads a moving target, so re-run the command if it errors out once.

## The antipattern markers

Every deliberately wrong line in this repository carries a fixed, greppable comment so no one mistakes a teaching bug for a pattern to copy:

```text
# ANTIPATTERN (deliberate, for teaching): <why it is wrong>. Correct: <the right approach>. Do not copy.
```

List every intentional bug, mistuning, and disabled safety with:

```console
grep -rn "ANTIPATTERN (deliberate, for teaching)" src/
```

That command surfaces the `time.sleep` call, the `maximum_attempts=1` retry policy, the victim's `schedule_to_start_timeout`, and the `max_concurrent_activities=2` mistuning.

## Tutorial

A full walkthrough of the mechanism lives on masonegger.com.

TODO: link the published tutorial on masonegger.com once it is live.

## License

[MIT](LICENSE), copyright 2026 Mason Egger.
</content>
