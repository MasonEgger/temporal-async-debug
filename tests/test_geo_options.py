"""ABOUTME: Tests for geo_activity_options, the pure activity-timeout helper.
ABOUTME: Confirms the one fixed start_to_close/schedule_to_close set and the default retry policy.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from temporal_async_debug.workflow import (
    GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
    GEO_START_TO_CLOSE_TIMEOUT,
    geo_activity_options,
)


@pytest.mark.parametrize("mode", ["block", "cpu"])
def test_geo_activity_options_is_one_fixed_set(mode: str) -> None:
    """Both modes get the same budgets, no heartbeat_timeout, and the default retry policy."""
    options = geo_activity_options(mode)
    assert options.start_to_close_timeout == timedelta(seconds=120)
    assert options.schedule_to_close_timeout == timedelta(seconds=150)
    assert options.start_to_close_timeout == GEO_START_TO_CLOSE_TIMEOUT
    assert options.schedule_to_close_timeout == GEO_SCHEDULE_TO_CLOSE_TIMEOUT
    assert not hasattr(options, "heartbeat_timeout")
    assert not hasattr(options, "retry_policy")


def test_geo_activity_options_rejects_an_unknown_mode() -> None:
    """A typo'd mode raises instead of silently producing default options."""
    with pytest.raises(ValueError, match="unknown mode"):
        geo_activity_options("not-a-real-mode")
