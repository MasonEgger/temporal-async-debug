"""ABOUTME: Stub for the Part D heartbeat test; you write the body.
ABOUTME: The finished version lives in ../solution/tests/test_heartbeat.py.
"""

from __future__ import annotations

import pytest


async def test_a_poll_wait_heartbeats_and_does_not_starve_the_loop() -> None:
    """One poll wait records at least two heartbeats and leaves no probe gap near the wait's length."""
    # TODO PART D: Shrink the timings in activities.py (POLL_INTERVAL_SECONDS, TICK_SECONDS, JOB_SECONDS) with
    # monkeypatch so the job needs one poll wait that spans several ticks. Run get_location under
    # ActivityEnvironment with on_heartbeat counting calls, beside a probe that records a timestamp every 50 ms.
    # Assert at least two heartbeats and that no gap between ticks reaches 0.2 seconds, so the test fails
    # until the fix is in.
    pytest.fail("TODO PART D: write the heartbeat test")
