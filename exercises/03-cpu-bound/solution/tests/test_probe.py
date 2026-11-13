"""ABOUTME: Deterministic, Temporal-free proof that the CPU-bound transform does not starve the event loop.
ABOUTME: A 50 ms probe ticks beside get_location, run the way the worker runs it, with a calibrated work size.

The worker runs an ``async def`` activity on its one event loop and a ``def`` activity on its
``activity_executor``. This test runs get_location the same way, with a work size calibrated to about
one second of hashing on the machine at hand. A probe coroutine records a timestamp every 50 ms.
If the transform holds the loop, one probe gap balloons to the length of the work. On the executor,
the pool thread shares the GIL with the loop thread, so the loop keeps ticking and every gap stays
near the tick interval.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from activities import _stretch_digest, get_location
from conftest import MOCKED_IP
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from worker import build_worker

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor

    import respx

TICK_INTERVAL_SECONDS: float = 0.05
"""How long the probe parks between ticks."""

WORK_SECONDS: float = 1.0
"""How long the calibrated transform should run, long enough to show as one big gap if it holds the loop."""

CALIBRATION_ROUNDS: int = 100_000
"""Rounds timed once to learn how fast this machine hashes."""

COOPERATIVE_GAP_CEILING_SECONDS: float = 0.2
"""Every probe gap must stay under this, four times the tick interval, so jitter cannot trip it."""


def _rounds_for(seconds: float) -> int:
    """Return the round count that takes about ``seconds`` of hashing on this machine."""
    started = time.perf_counter()
    _stretch_digest("calibration", CALIBRATION_ROUNDS)
    elapsed = time.perf_counter() - started
    return max(1, round(CALIBRATION_ROUNDS * seconds / elapsed))


async def _run_like_the_worker(
    environment: ActivityEnvironment,
    activity_fn: Callable[..., object],
    executor: Executor | None,
    *args: object,
) -> None:
    """Run an activity where the worker would: async def on the loop, def on the executor."""
    if inspect.iscoroutinefunction(activity_fn):
        await environment.run(activity_fn, *args)
        return
    assert executor is not None, "a def activity needs the worker's activity_executor"
    await asyncio.get_running_loop().run_in_executor(executor, environment.run, activity_fn, *args)


async def _record_probe_gaps(executor: Executor | None, work_rounds: int) -> list[float]:
    """Run get_location beside a ticking probe and return the gaps between consecutive ticks."""
    tick_timestamps: list[float] = []
    activity_done = asyncio.Event()

    async def probe() -> None:
        while not activity_done.is_set():
            tick_timestamps.append(time.monotonic())
            await asyncio.sleep(TICK_INTERVAL_SECONDS)
        # One last tick: a freeze that outlasts the activity shows up as the gap before it.
        tick_timestamps.append(time.monotonic())

    async def run_activity() -> None:
        try:
            await _run_like_the_worker(ActivityEnvironment(), get_location, executor, MOCKED_IP, work_rounds)
        finally:
            activity_done.set()

    await asyncio.gather(probe(), run_activity())
    return [later - earlier for earlier, later in zip(tick_timestamps, tick_timestamps[1:], strict=False)]


async def test_get_location_does_not_starve_the_event_loop(mocked_network: respx.MockRouter) -> None:
    """With the worker's activity_executor in play, the probe ticks through the transform."""
    work_rounds = _rounds_for(WORK_SECONDS)
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        executor = build_worker(environment.client).config()["activity_executor"]
        assert isinstance(executor, ThreadPoolExecutor)
        try:
            gaps = await _record_probe_gaps(executor, work_rounds)
        finally:
            executor.shutdown(wait=False)

    assert mocked_network.calls.call_count == 1
    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) < COOPERATIVE_GAP_CEILING_SECONDS
