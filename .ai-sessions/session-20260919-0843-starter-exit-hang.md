# Session Summary: Fix the Starter Exit Hang

**Date**: 2026-09-19
**Duration**: Background investigation, roughly 40 minutes of subagent work
**Conversation Turns**: part of a larger design session
**Estimated Cost**: Moderate; one long-running diagnostic subagent (bisect plus live repro)
**Model**: Fable 5 orchestrating; Sonnet subagent for the live diagnosis

## Key Actions

- Diagnosed the intermittent hang where the starter printed all its results and then never exited (0% CPU, futex_wait, teardown-time).
- Bisected with standalone repros against a real worker: httpx metrics polling alone, bare execute_workflow, bare start_workflow plus handle.result(), and a hand-copied full slot-exhaustion path each ran 20/20 clean. Only the real starter reproduced the hang (~5-10% of runs), confirming the cause is not in the new httpx or start_workflow logic.
- Root cause: temporalio's default Core runtime owns a process-wide Tokio thread pool with no public close/shutdown on Client or Runtime in temporalio 1.33. It is torn down only during CPython interpreter finalization, which intermittently races a Tokio worker thread reacquiring the GIL; the worker thread parks forever and the process hangs. This is the open upstream issue temporalio/sdk-python#300. Inspecting two live hangs via /proc showed exactly the two-thread parked shape (main thread in futex_wait, tokio-rt-worker in pause).
- Fix (starter.py only): after asyncio.run(main()), flush stdout/stderr and os._exit(0) on the success path, skipping the finalization phase where the race lives. An exception from main() still propagates normally. This is the maintainer-suggested mitigation for a short-lived process; there is no public client/runtime close to call instead.
- Verified: 40/40 clean exits post-fix, one real just slow end to end, just check green (39 tests, ruff, mypy).

## Observations

- The demo is about blocking the event loop, and the fix itself is a second, subtler Python/Temporal footgun (a runtime-teardown GIL race). Worth a mention in the eventual tutorial as a real-world "even exiting cleanly is not free" aside.
- This lands right before a larger redesign (two neutrally-named workflow types, cross-type blast radius, drop heartbeats, realistic timeouts) that rewrites starter.py; the os._exit workaround carries forward into that rewrite.

## Suggested Skills for Next Session

- `python:python` and `temporal:temporal-developer`: the upcoming redesign rewrites the workflows, activities, worker, and starter.
