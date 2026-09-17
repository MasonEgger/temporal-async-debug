"""ABOUTME: Deterministic, Temporal-free proof that block mode freezes the event loop and slow mode does not.
ABOUTME: A probe ticks on an asyncio timer beside _apply_mode; block starves its ticks, slow spares them.

The worker's whole failure mode is one event loop that a synchronous time.sleep can freeze. This test
reproduces that contrast without a Temporal server. A probe coroutine records a monotonic timestamp every
50 ms while _apply_mode runs beside it, exactly as the worker runs its poller beside an activity. In block
mode the real time.sleep stops the loop, so the probe misses ticks and one gap balloons past the block's
length. In slow mode the cooperative asyncio.sleep leaves the loop free, so every gap stays near the tick
interval and the probe records strictly more ticks over the same wall-clock window.
"""

from __future__ import annotations

import asyncio
import time

from temporal_async_debug.activities import _apply_mode

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


async def test_block_mode_starves_the_probe() -> None:
    """The real time.sleep in block mode freezes the loop, so one probe gap dwarfs the tick interval."""
    timestamps = await _record_probe_ticks("block", BLOCK_SECONDS)

    gaps = _consecutive_gaps(timestamps)

    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) > STARVED_GAP_THRESHOLD_SECONDS


async def test_slow_mode_keeps_the_probe_ticking() -> None:
    """Cooperative asyncio.sleep leaves the loop free, so every probe gap stays near the tick interval."""
    timestamps = await _record_probe_ticks("slow", BLOCK_SECONDS)

    gaps = _consecutive_gaps(timestamps)

    assert gaps, "the probe recorded too few ticks to measure a gap"
    assert max(gaps) < COOPERATIVE_GAP_CEILING_SECONDS


async def test_block_mode_records_fewer_ticks_than_slow_mode() -> None:
    """Over one identical window the frozen loop ticks strictly fewer times than the cooperative one."""
    block_ticks = await _record_probe_ticks("block", BLOCK_SECONDS)
    slow_ticks = await _record_probe_ticks("slow", BLOCK_SECONDS)

    assert len(block_ticks) < len(slow_ticks)
