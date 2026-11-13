# Session Summary: Goal Step 7, Exercise 03 CPU Bound

**Date**: 2026-11-03
**Duration**: One autonomous step (implement, validate, one comments-only fix pass, finalize)
**Conversation Turns**: Few (dispatch-driven)
**Estimated Cost**: Moderate
**Model**: Sonnet 5.5 (finalize)

## Goal Context

Step 7 of the `/bpe:goal` run over the regenerated 14-step plan.
Creates exercises/03-cpu-bound/ with a solution/ and a practice/ copy.

## Key Actions

- Built the solution copy: `def get_location` on `httpx.Client` running on a ThreadPoolExecutor, with the CPU transform kept and no marker.
- Built the practice copy: `async def get_location` on `httpx.AsyncClient` with the GIL-pinning transform, marker kept, `# TODO PART C` on the signature and above the client line, and `# TODO PART D`.
- Ticked the Step 7 checkboxes in `todo.md`.
- `just check` and `just check-practice` both exit 0.
- Validated clean at iteration 2 after one comments-only fix pass.

## As-Built Design

- The transform is `_stretch_digest(seed, rounds)`: bounded SHA-256 chaining over the location.
  It is count-bounded, with no clock, fork, or subprocess.
- `BAD_WORK_ROUNDS` is 40,000,000, measured at about 25 s on this machine.
  `HEALTHY_WORK_ROUNDS` is 1,000.
- `get_ip` stays `async def` on `httpx.AsyncClient` in both copies.
- Practice `get_location` is `async def` on `AsyncClient`.
  Solution `get_location` is `def` on `httpx.Client`.
- Starter is carried over from 02, with no slow endpoint.
- The probe calibrates the work to about 1 s at test time.

## Live Smoke (from implement)

- Practice: the rollup failed with "Activity task timed out", receipts stalled about 24.9 s then completed, and the worker sat at 100.0 %CPU during the freeze.
- Solution: the fleet completed, with CPU near 100 percent on the pool thread.
- py-spy and `asyncio ps` were not captured, so Step 10 must capture them.

## Findings for Step 10 and Step 11

- The freeze starts only after `get_location`'s live geo round trip, so `FREEZE_LOCK_GUARD_SECONDS` 1.0 may not cover a slow provider.
  Step 10 must confirm the receipts stall.
- The roughly 25 s is machine-specific.
  On a faster machine the rollup may show only StartToClose.
  The Step 11 README should say the duration scales with CPU speed.
- 03's practice uses the async HTTP client where 01's uses the sync one.
  The README should say so.

## Prompt Inventory

| Prompt/Command | Action Taken | Outcome |
|---|---|---|
| Mode: implement, Step 7 | Created both exercise copies, live smoke | Tests green, smoke showed the freeze |
| Mode: fix, iteration 1 | Applied comments-only validator findings | Validated clean at iteration 2 |
| Mode: finalize, Step 7 | Ran both gates, wrote this summary, committed and pushed | See commit |

## Observations

- `git status --porcelain --untracked-files=all exercises/` lists only source and test files, no caches.
- No lesson added; nothing novel beyond the findings above.
