"""ABOUTME: Deterministic, Temporal-free regression guard: no async def activity may starve the event loop.
ABOUTME: A 50 ms probe ticks beside every async def activity the worker registers, with inputs mocked.

The worker runs every ``async def`` activity on its one event loop, so one that does synchronous work
holds the loop for as long as the work lasts, and every other workflow on the worker waits it out.
This test takes the worker's registered activities, keeps the ``async def`` ones, and runs each
body beside a probe coroutine that records a timestamp every 50 ms. If an activity holds the loop,
one probe gap balloons to the length of the work.

The network is mocked, and get_location gets a payload calibrated to about 0.6 seconds of
archiving on the machine at hand, so a version that archives on the loop stalls the probe
clearly past the 0.2 second ceiling. An activity with no entry in ACTIVITY_INPUTS fails the test, so
a new async activity cannot reach the worker without a probe.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import TYPE_CHECKING, Any

import pytest
from activities import _archive_audit_trail
from conftest import MOCKED_IP
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from worker import ACTIVITIES, build_worker

if TYPE_CHECKING:
    from collections.abc import Callable

    import respx

TICK_INTERVAL_SECONDS: float = 0.05
"""How long the probe parks between ticks."""

STALL_SECONDS: float = 0.6
"""How long get_location's archiving should take on the loop, so a stall shows as one big gap."""

CALIBRATION_RECORDS: int = 5_000
"""Records archived once to learn how fast this machine does the work."""

COOPERATIVE_GAP_CEILING_SECONDS: float = 0.2
"""Every probe gap must stay under this, four times the tick interval, so jitter cannot trip it."""


def _records_for(seconds: float) -> int:
    """Return the record count whose archiving takes about ``seconds`` on this machine."""
    started = time.perf_counter()
    _archive_audit_trail("calibration", CALIBRATION_RECORDS)
    elapsed = time.perf_counter() - started
    return max(1, round(CALIBRATION_RECORDS * seconds / elapsed))


ACTIVITY_INPUTS: dict[str, Callable[[], tuple[object, ...]]] = {
    "get_ip": lambda: (),
    "get_location": lambda: (MOCKED_IP, _records_for(STALL_SECONDS)),
    "validate_order": lambda: ("order-1", 3),
    "compute_total": lambda: (3, 1999),
    "format_receipt": lambda: ("order-1", 5997),
    "roll_up_sales": lambda: ("2026-01", 0.0),
}
"""Inputs for each registered async activity, by name. The network and the payload are mocked or small."""


ASYNC_ACTIVITIES: list[Callable[..., Any]] = [fn for fn in ACTIVITIES if inspect.iscoroutinefunction(fn)]
"""Every ``async def`` activity the worker registers, taken from the list build_worker uses."""


async def test_every_registered_async_activity_has_probe_inputs() -> None:
    """The activities a built Worker registers are the ones probed, and each has inputs."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        registered = build_worker(environment.client).config()["activities"]
    registered_async = {fn.__name__ for fn in registered if inspect.iscoroutinefunction(fn)}
    assert registered_async == {fn.__name__ for fn in ASYNC_ACTIVITIES}
    assert registered_async == set(ACTIVITY_INPUTS)


async def _record_probe_gaps(activity_fn: Callable[..., Any], args: tuple[object, ...]) -> list[float]:
    """Run the activity beside a ticking probe and return the gaps between consecutive ticks."""
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
            await ActivityEnvironment().run(activity_fn, *args)
        finally:
            activity_done.set()

    await asyncio.gather(probe(), run_activity())
    return [later - earlier for earlier, later in zip(tick_timestamps, tick_timestamps[1:], strict=False)]


@pytest.mark.parametrize("activity_fn", ASYNC_ACTIVITIES, ids=lambda fn: fn.__name__)
async def test_async_activity_does_not_starve_the_event_loop(
    activity_fn: Callable[..., Any], mocked_network: respx.MockRouter
) -> None:
    """With the network mocked, the probe ticks through every async activity without a long gap."""
    args = ACTIVITY_INPUTS[activity_fn.__name__]()

    gaps = await _record_probe_gaps(activity_fn, args)

    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) < COOPERATIVE_GAP_CEILING_SECONDS
