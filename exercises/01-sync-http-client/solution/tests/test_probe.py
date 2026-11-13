"""ABOUTME: Deterministic, Temporal-free proof that the geo activity does not starve the event loop.
ABOUTME: A 50 ms probe ticks beside get_location, run the way the worker runs it, against a local slow endpoint.

The worker runs an ``async def`` activity on its one event loop and a ``def`` activity on its
``activity_executor``. This test runs get_location the same way against a stdlib server that waits
half a second before it answers. A probe coroutine records a timestamp every 50 ms. If get_location
holds the loop through that wait, one probe gap balloons to the wait's length. On the executor,
every gap stays near the tick interval.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from activities import get_location
from conftest import MOCKED_IP
from slow_upstream import serve_slow_upstream
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from worker import build_worker

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Executor

TICK_INTERVAL_SECONDS: float = 0.05
"""How long the probe parks between ticks."""

UPSTREAM_DELAY_SECONDS: float = 0.5
"""How long the local endpoint waits before it answers."""

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


async def _record_probe_gaps(executor: Executor | None, upstream_url: str) -> list[float]:
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
            await _run_like_the_worker(ActivityEnvironment(), get_location, executor, MOCKED_IP, upstream_url)
        finally:
            activity_done.set()

    await asyncio.gather(probe(), run_activity())
    return [later - earlier for earlier, later in zip(tick_timestamps, tick_timestamps[1:], strict=False)]


async def test_get_location_does_not_starve_the_event_loop() -> None:
    """With the worker's activity_executor in play, the probe ticks through the upstream's wait."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        executor = build_worker(environment.client).config()["activity_executor"]
        assert isinstance(executor, ThreadPoolExecutor)
        try:
            with serve_slow_upstream(UPSTREAM_DELAY_SECONDS) as upstream_url:
                gaps = await _record_probe_gaps(executor, upstream_url)
        finally:
            executor.shutdown(wait=False)

    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) < COOPERATIVE_GAP_CEILING_SECONDS
