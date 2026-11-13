"""ABOUTME: Proof that get_location heartbeats during a poll wait and does not starve the event loop.
ABOUTME: It runs the activity under ActivityEnvironment, counts heartbeats, and ticks a 50 ms probe beside it.

The workflow's heartbeat_timeout is shorter than get_location's poll interval, so the activity has to
heartbeat while it waits. An ``async def`` activity heartbeats through the event loop, so a blocking wait
(``time.sleep``) records one heartbeat and then holds the loop until the wait ends. This test shrinks the
timings so the job needs exactly one poll wait: the first poll finds the job running, the activity waits,
and the second poll finds it done. The wait is made to span many ticks, so the awaited form heartbeats
several times and keeps the probe ticking, and the blocking form does neither.
"""

from __future__ import annotations

import asyncio
import time

import activities
import pytest
from activities import get_location
from conftest import MOCKED_IP
from temporalio.testing import ActivityEnvironment

POLL_INTERVAL_SECONDS: float = 0.5
"""The shrunken poll interval the test runs under; one wait spans five ticks."""

TICK_SECONDS: float = 0.1
"""The shrunken tick length the test runs under."""

JOB_SECONDS: float = 0.3
"""The shrunken job length; shorter than one poll interval, so exactly one wait is needed."""

PROBE_INTERVAL_SECONDS: float = 0.05
"""How long the probe parks between ticks."""

COOPERATIVE_GAP_CEILING_SECONDS: float = 0.2
"""Every probe gap must stay under this, four times the probe interval, so jitter cannot trip it."""


@pytest.fixture(autouse=True)
def shrunken_timings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the poll timings so one poll wait is half a second and the job needs one wait."""
    monkeypatch.setattr(activities, "POLL_INTERVAL_SECONDS", POLL_INTERVAL_SECONDS)
    monkeypatch.setattr(activities, "TICK_SECONDS", TICK_SECONDS)
    monkeypatch.setattr(activities, "JOB_SECONDS", JOB_SECONDS)
    monkeypatch.setattr(activities, "_JOB_STARTED_AT", {})


async def test_a_poll_wait_heartbeats_and_does_not_starve_the_loop() -> None:
    """One poll wait records at least two heartbeats and leaves no probe gap near the wait's length."""
    heartbeat_count = 0
    tick_timestamps: list[float] = []
    activity_done = asyncio.Event()

    def count_heartbeat(*_details: object) -> None:
        nonlocal heartbeat_count
        heartbeat_count += 1

    environment = ActivityEnvironment()
    environment.on_heartbeat = count_heartbeat

    async def probe() -> None:
        while not activity_done.is_set():
            tick_timestamps.append(time.monotonic())
            await asyncio.sleep(PROBE_INTERVAL_SECONDS)
        # One last tick: a freeze that outlasts the activity shows up as the gap before it.
        tick_timestamps.append(time.monotonic())

    async def run_activity() -> str:
        try:
            return await environment.run(get_location, MOCKED_IP, True)
        finally:
            activity_done.set()

    _, location = await asyncio.gather(probe(), run_activity())

    gaps = [later - earlier for earlier, later in zip(tick_timestamps, tick_timestamps[1:], strict=False)]
    assert location == activities.JOB_RESULT
    assert heartbeat_count >= 2
    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) < COOPERATIVE_GAP_CEILING_SECONDS
