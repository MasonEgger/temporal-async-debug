"""ABOUTME: Tests for geo_activity_options, the pure per-mode activity-timeout helper.
ABOUTME: Confirms each mode's start_to_close/schedule_to_close/heartbeat_timeout/retry contract.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from temporal_async_debug.workflow import (
    GEO_HEARTBEAT_TIMEOUT,
    GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
    GEO_START_TO_CLOSE_TIMEOUT,
    geo_activity_options,
)

MODES_WITHOUT_HEARTBEAT: tuple[str, ...] = ("block", "cpu", "slow")
"""Modes whose options carry no heartbeat_timeout: frozen-loop modes and the silent cooperative one."""

MODES_WITH_HEARTBEAT: tuple[str, ...] = ("slow_heartbeat", "stuck_no_heartbeat")
"""Modes whose options carry a heartbeat_timeout: one satisfies it, one never does."""


@pytest.mark.parametrize("mode", MODES_WITHOUT_HEARTBEAT)
def test_geo_activity_options_has_no_heartbeat_timeout(mode: str) -> None:
    """block, cpu, and slow get a generous start_to_close and no heartbeat_timeout."""
    options = geo_activity_options(mode)
    assert options.start_to_close_timeout == timedelta(seconds=120)
    assert options.heartbeat_timeout is None


@pytest.mark.parametrize("mode", MODES_WITH_HEARTBEAT)
def test_geo_activity_options_sets_a_heartbeat_timeout(mode: str) -> None:
    """slow_heartbeat and stuck_no_heartbeat both get a generous start_to_close and a heartbeat_timeout."""
    options = geo_activity_options(mode)
    assert options.start_to_close_timeout == timedelta(seconds=120)
    assert options.heartbeat_timeout == timedelta(seconds=10)


@pytest.mark.parametrize("mode", MODES_WITHOUT_HEARTBEAT + MODES_WITH_HEARTBEAT)
def test_geo_activity_options_sets_schedule_to_close_and_disables_retries(mode: str) -> None:
    """Every mode shares the same schedule_to_close budget and the marked maximum_attempts=1 policy."""
    options = geo_activity_options(mode)
    assert options.schedule_to_close_timeout == timedelta(seconds=150)
    assert options.retry_policy.maximum_attempts == 1


def test_geo_activity_options_module_constants_match_the_returned_values() -> None:
    """The module-level timeout constants are the values geo_activity_options actually returns."""
    options = geo_activity_options("block")
    assert options.start_to_close_timeout == GEO_START_TO_CLOSE_TIMEOUT
    assert options.schedule_to_close_timeout == GEO_SCHEDULE_TO_CLOSE_TIMEOUT
    assert geo_activity_options("slow_heartbeat").heartbeat_timeout == GEO_HEARTBEAT_TIMEOUT


def test_geo_activity_options_rejects_an_unknown_mode() -> None:
    """A typo'd mode raises instead of silently producing default options."""
    with pytest.raises(ValueError, match="unknown mode"):
        geo_activity_options("not-a-real-mode")
