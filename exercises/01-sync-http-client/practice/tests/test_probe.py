"""ABOUTME: Stub for the Part D starvation-probe test; you write the body.
ABOUTME: The finished version lives in ../solution/tests/test_probe.py.
"""

from __future__ import annotations

import pytest


async def test_get_location_does_not_starve_the_event_loop() -> None:
    """The probe ticks through the upstream's wait while get_location runs."""
    # TODO PART D: Serve the slow endpoint from slow_upstream.py, run get_location beside a probe that
    # records a timestamp every 50 ms, and assert that no gap between ticks reaches 0.2 seconds.
    # Run the activity the way the worker would, so the test fails until the fix is in.
    pytest.fail("TODO PART D: write the probe test")
