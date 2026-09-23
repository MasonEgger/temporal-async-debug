"""ABOUTME: Deterministic, Temporal-free proof that freezing modes starve the event loop and cooperative modes do not.
ABOUTME: A probe ticks on an asyncio timer beside _apply_mode; block and cpu starve it, slow and slow_heartbeat do not.

The worker's whole failure mode is one event loop that an uncancellable wait can freeze. This test
reproduces that contrast without a Temporal server. A probe coroutine records a monotonic timestamp every
50 ms while _apply_mode runs beside it, exactly as the worker runs its poller beside an activity. The
modes fall into two families: block (a real time.sleep) and cpu (a busy loop pinning the GIL) both freeze
the loop, so the probe misses ticks and one gap balloons past their length. slow and slow_heartbeat both
await asyncio.sleep, cooperative even though slow_heartbeat also heartbeats between steps, so every gap
stays near the tick interval and the probe records strictly more ticks over the same wall-clock window.
slow_heartbeat's activity.heartbeat call is guarded by activity.in_activity(), so it runs Temporal-free here.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from temporal_async_debug.activities import _apply_mode

FREEZING_MODES: tuple[str, ...] = ("block", "cpu")
"""Uncancellable waits that pin the event loop for their full duration."""

COOPERATIVE_MODES: tuple[str, ...] = ("slow", "slow_heartbeat")
"""Awaited waits that yield the event loop back to the probe between steps."""

TICK_INTERVAL_SECONDS: float = 0.05
"""How long the probe parks between ticks; short enough that a 0.5 s block is unmistakable."""

BLOCK_SECONDS: float = 0.5
"""Delay handed to _apply_mode: a real time.sleep in block mode, a real asyncio.sleep in slow mode."""

PROBE_WINDOW_SECONDS: float = 0.8
"""Wall-clock window the probe runs for, long enough to tick well past the block yet keep the test fast."""

STARVED_GAP_THRESHOLD_SECONDS: float = 0.4
"""A block-mode gap must clear this; the 0.5 s freeze leaves generous room above it."""

COOPERATIVE_GAP_CEILING_SECONDS: float = 0.2
"""Every slow-mode gap must stay under this, four times the tick interval, so jitter cannot trip it."""


async def _record_probe_ticks(mode: str, block_seconds: float) -> list[float]:
    """Run the probe beside _apply_mode and return the monotonic timestamp of each tick.

    The probe and the delay run concurrently on one event loop, the same arrangement that lets a
    blocking activity starve the worker. A blocking delay stops the probe; a cooperative one does not.

    Args:
        mode: Passed straight to _apply_mode: "block" freezes the loop, "slow" yields it.
        block_seconds: Delay _apply_mode applies once, in seconds.

    Returns:
        One monotonic timestamp per probe tick, in the order they were recorded.
    """
    tick_timestamps: list[float] = []

    async def probe() -> None:
        deadline = time.monotonic() + PROBE_WINDOW_SECONDS
        while time.monotonic() < deadline:
            tick_timestamps.append(time.monotonic())
            await asyncio.sleep(TICK_INTERVAL_SECONDS)

    async def apply_delay() -> None:
        await _apply_mode(mode, block_seconds)

    await asyncio.gather(probe(), apply_delay())
    return tick_timestamps


def _consecutive_gaps(timestamps: list[float]) -> list[float]:
    """Return the elapsed seconds between each pair of consecutive timestamps."""
    return [later - earlier for earlier, later in zip(timestamps, timestamps[1:], strict=False)]


@pytest.mark.parametrize("mode", FREEZING_MODES)
async def test_freezing_modes_starve_the_probe(mode: str) -> None:
    """block's real time.sleep and cpu's busy loop both freeze the loop, so one gap dwarfs the tick interval."""
    timestamps = await _record_probe_ticks(mode, BLOCK_SECONDS)

    gaps = _consecutive_gaps(timestamps)

    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) > STARVED_GAP_THRESHOLD_SECONDS


@pytest.mark.parametrize("mode", COOPERATIVE_MODES)
async def test_cooperative_modes_keep_the_probe_ticking(mode: str) -> None:
    """slow and slow_heartbeat both await the loop free, so every probe gap stays near the tick interval."""
    timestamps = await _record_probe_ticks(mode, BLOCK_SECONDS)

    gaps = _consecutive_gaps(timestamps)

    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) < COOPERATIVE_GAP_CEILING_SECONDS


async def test_block_mode_records_fewer_ticks_than_slow_mode() -> None:
    """Over one identical window the frozen loop ticks strictly fewer times than the cooperative one."""
    block_ticks = await _record_probe_ticks("block", BLOCK_SECONDS)
    slow_ticks = await _record_probe_ticks("slow", BLOCK_SECONDS)

    assert len(block_ticks) < len(slow_ticks)


async def test_cpu_mode_records_fewer_ticks_than_slow_heartbeat_mode() -> None:
    """Over one identical window the GIL-pinned loop ticks strictly fewer times than the heartbeating one."""
    cpu_ticks = await _record_probe_ticks("cpu", BLOCK_SECONDS)
    slow_heartbeat_ticks = await _record_probe_ticks("slow_heartbeat", BLOCK_SECONDS)

    assert len(cpu_ticks) < len(slow_heartbeat_ticks)
