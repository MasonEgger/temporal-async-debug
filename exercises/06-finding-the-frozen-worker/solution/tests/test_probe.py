"""ABOUTME: Deterministic, Temporal-free proof that the geo activity does not starve the event loop.
ABOUTME: A 50 ms probe ticks beside get_location, run the way the worker runs it, while the test holds the cache lock.

The worker runs an ``async def`` activity on its one event loop and a ``def`` activity on its
``activity_executor``. This test runs get_location the same way against a location cache whose
lock the test holds for 0.6 seconds, so the lookup's SELECT waits that long. A probe coroutine
records a timestamp every 50 ms. If get_location holds the loop through that wait, one probe gap
balloons to the wait's length. On the executor, every gap stays near the tick interval.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from activities import get_location
from conftest import MOCKED_IP
from db_lock import hold_cache_lock
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from worker import build_worker

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor
    from pathlib import Path

    import respx

TICK_INTERVAL_SECONDS: float = 0.05
"""How long the probe parks between ticks."""

LOCK_HOLD_SECONDS: float = 0.6
"""How long the test holds the cache lock after it arms it."""

COOPERATIVE_GAP_CEILING_SECONDS: float = 0.2
"""Every probe gap must stay under this, four times the tick interval, so jitter cannot trip it."""


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


async def _record_probe_gaps(executor: Executor | None, location_cache_path: str) -> list[float]:
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
            await _run_like_the_worker(ActivityEnvironment(), get_location, executor, MOCKED_IP, location_cache_path)
        finally:
            activity_done.set()

    await asyncio.gather(probe(), run_activity())
    return [later - earlier for earlier, later in zip(tick_timestamps, tick_timestamps[1:], strict=False)]


async def test_get_location_does_not_starve_the_event_loop(mocked_network: respx.MockRouter, tmp_path: Path) -> None:
    """With the worker's activity_executor in play, the probe ticks through the lock wait."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        executor = build_worker(environment.client).config()["activity_executor"]
        assert isinstance(executor, ThreadPoolExecutor)
        try:
            with hold_cache_lock(LOCK_HOLD_SECONDS, tmp_path) as lock:
                lock.arm()
                gaps = await _record_probe_gaps(executor, str(lock.database_path))
        finally:
            executor.shutdown(wait=False)

    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) < COOPERATIVE_GAP_CEILING_SECONDS
    # The cache is empty, so the lookup missed and fell through to the mocked provider.
    assert mocked_network.calls.call_count == 1
