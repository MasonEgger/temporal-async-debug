"""ABOUTME: Stub for the Part D starvation-probe test; you write the body.
ABOUTME: The finished version lives in ../solution/tests/test_probe.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    import respx


async def test_get_location_does_not_starve_the_event_loop(mocked_network: respx.MockRouter, tmp_path: Path) -> None:
    """The probe ticks through the cache lookup's lock wait while get_location runs."""
    # TODO PART D: Hold the cache lock with hold_cache_lock from db_lock.py and arm it, then run
    # get_location beside a probe that records a timestamp every 50 ms, and assert that no gap between
    # ticks reaches 0.2 seconds. Run the activity the way the worker would, so the test fails until the
    # fix is in.
    pytest.fail("TODO PART D: write the probe test")
