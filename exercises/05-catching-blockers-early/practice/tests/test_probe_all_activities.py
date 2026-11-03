"""ABOUTME: Stub for the Part D probe test over every async activity; you write the body.
ABOUTME: The finished version lives in ../solution/tests/test_probe_all_activities.py.
"""

from __future__ import annotations

import pytest


async def test_async_activities_do_not_starve_the_event_loop() -> None:
    """The probe ticks through every async def activity the worker registers."""
    # TODO PART D: Take the worker's registered activities (worker.ACTIVITIES, so the test can
    # parametrize at collection time) and keep the async def ones. Run each body beside a probe that
    # records a timestamp every 50 ms, with the network mocked and get_location's payload sized so
    # that archiving it on the loop takes well over 0.2 seconds. Assert that no gap between ticks reaches
    # 0.2 seconds, for every activity.
    # The test should fail until the fix is in.
    pytest.fail("TODO PART D: write the probe test")
