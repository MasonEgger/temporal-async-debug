# Field Evidence Review: Blocking The Python Event Loop

**Date**: 2026-11-09
**Purpose**: check whether the exercises reflect what Temporal Python users actually hit, and decide between new exercises and changes to existing ones.
**Privacy**: this repository is public.
This file summarizes the evidence in aggregate only.
It names no customer, no company (real or invented), no namespace, no ticket, and no specific use case.
The raw research notes stay outside the repository.

## Method

Read-only research agents reviewed field reports of blocked event loops in Temporal Python Workers.
Each recorded, per case, the blocker, the symptom, how it was diagnosed, the fix, misconceptions, and which exercise it maps to.
Each applied one test to every recommendation: a separate exercise is justified only when the reader performs a distinct skill (a different symptom to read, a different diagnosis path, or a different fix) and the case is common.

Coverage limits:

- The review found about 50 cases, and the counts below are approximate.
- The review was not exhaustive: some sources were not searched, and some documents could not be read.

## What blocks the loop

Most common first, counts approximate across sources:

1. A synchronous client inside `async def`, by a wide margin (about 10 or more cases): LLM SDK calls, cloud SDK calls, database drivers and ORMs (including ORM calls wrapped in a single-thread sync-to-async adapter), message producers that flush synchronously, and in-house packages that are synchronous underneath.
2. CPU-bound work and GIL contention (about 5 to 8 cases), including very large fan-outs of asyncio tasks on a single-CPU Worker and telemetry export.
3. Logging locks and synchronous telemetry (2 to 4 cases), often near-misses.
4. Payload codecs and key-management calls (3 cases), latent or suspected, never confirmed as the root cause.
5. `time.sleep` (1 case).

## How it shows up

- Workflow Task timeouts in nearly every case.
- `TMPRL1101 Potential deadlock detected` on Workflow code that was fine (8 or more cases).
- Workers that stop picking up work while the process stays alive (10 or more).
- The Worker log line "Task not found when completing" (seen in 8 or more separate reports).
- An Activity marked Started minutes before its code ran (3).
- Free slots, green health checks, and a Worker still reported alive, because the Rust core keeps polling and heartbeating the Worker.

## How it was actually diagnosed

- A single question, "are these `async def`, and what do they call?", followed by reading the code.
- Bisecting from a hello-world sample, or reproducing locally with `time.sleep`.
- Continuous profiling.
- Matching failures to one host.
- One team built its own production loop-lag detector.

What did not appear in practice:

- `python -m asyncio ps` never appeared, which is expected for a Python 3.14 tool.
- `py-spy` appeared once and was inconclusive.
- asyncio debug mode was suggested four times and never reported as used.

Missing SDK metrics stalled several cases, and many took days to resolve.

## Misconceptions worth teaching against

- Activity code cannot affect Workflows.
- Two Workers in one process are isolated from each other.
- A policy of making everything async makes the code non-blocking.
- Raising timeouts, scaling out, adding pollers, or restarting fixes it.
- `TMPRL1101` always means the Workflow code deadlocked.
- `activity_executor` also runs `async def` Activities (one Worker passed a large thread pool that never ran anything).
- Arriving heartbeats prove the loop is healthy, and calling `heartbeat()` means a heartbeat was sent.
- Moving CPU-bound work to threads fixes it (the GIL contention continued).
- A blocked loop catches up on its own.

## Fixes that backfired or fell short

- Converting one Activity while another `async def` Worker in the same process kept blocking.
- Moving CPU-bound work to `def` plus threads, after which `TMPRL1101` continued.
- Wrapping code in `asyncio.run()` inside sync Activities.
- Restarts and more CPU, after which the problem returned.
- Background heartbeaters that ignore cancellation, the exercise 04 shape.
- Splitting Workflow and Activity Workers as a workaround instead of finding the blocker.

## Who hits it

LLM and AI application teams make up most cases from 2025 on.
Next come teams reusing existing synchronous packages, teams migrating from Celery or Django, and smaller teams without SDK metrics.
Experienced Python developers hit it too.

## Existing public content

- The public Python SDK sync-versus-async docs page came up in nearly every case.
  It teaches the rule but not the diagnosis, and days of guessing often follow.

## Verdict per exercise

| Exercise | Evidence | Recommendation |
|---|---|---|
| 01 sync client | Strongest | Keep. Add a "same bug, other library" table and frame the slow upstream as an LLM API, still on httpx. |
| 02 sleep between heartbeats | Thin for the retry storm, common for `TMPRL1101` | Keep. Lead with `TMPRL1101` as a misleading signal and with "calling `heartbeat()` is not sending it". Do not grow the storm. |
| 03 CPU-bound | Strong, with a catch | Make more Worker processes or a dedicated Task Queue the fix for sustained CPU work, not an extension. The transform hashes 32-byte digests and holds the GIL; with two slots the thread fix looks cleaner than it does at scale. |
| 04 zombie thread | No duplicate-work report, but the mechanism is real | Keep. Add "`activity_executor` only runs `def`" next to the startup traps. |
| 05 catching blockers early | A production loop-lag detector was built in the field | Add a production canary as the counterpart to the CI probe; shrink debug mode to a short step. |
| Fleet localization | Flagged independently by every source | New exercise 06 (ruled November 9, 2026; see spec.md). |

## Decisions

- Ruled: fleet localization becomes its own exercise, `06-finding-the-frozen-worker`, appended after 05 (spec.md).
- Open: reorder the exercises by field frequency (CPU second, the heartbeat exercise lower), or keep the numbering until publication.
- Open: open each Part B with the cheap diagnosis path (the code question, the histories, "Task not found when completing", Started versus the first log line) and use `asyncio ps` and `py-spy` as confirmation.
- Open: apply the per-exercise fold-ins in the table above.
- Kept out of scope: gevent compatibility, and loop overload from too many asyncio tasks, which is not a blocking call.
- Kept deferred: the codec and key-management blocker, and the registration guard (`flake8-async` covers part of it).
