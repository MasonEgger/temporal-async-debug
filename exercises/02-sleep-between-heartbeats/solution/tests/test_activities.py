"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the slow-job routing; test_heartbeat.py covers the heartbeats.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import activities
from activities import get_ip, get_location
from conftest import MOCKED_IP, MOCKED_LOCATION
from temporalio.testing import ActivityEnvironment

if TYPE_CHECKING:
    import pytest
    import respx


async def test_get_ip_returns_the_stripped_address(mocked_network: respx.MockRouter) -> None:
    """get_ip returns the first provider's body without its trailing newline."""
    assert await ActivityEnvironment().run(get_ip) == MOCKED_IP
    assert mocked_network.calls.call_count == 1


async def test_get_location_uses_the_public_providers_by_default(mocked_network: respx.MockRouter) -> None:
    """With slow_job unset, get_location asks the first public provider and parses its payload."""
    assert await ActivityEnvironment().run(get_location, MOCKED_IP, False) == MOCKED_LOCATION
    assert mocked_network.calls.call_count == 1


async def test_get_location_polls_the_slow_job_when_asked(
    mocked_network: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With slow_job set, get_location polls the simulated job and never asks the public providers."""
    monkeypatch.setattr(activities, "JOB_SECONDS", 0.2)
    monkeypatch.setattr(activities, "POLL_INTERVAL_SECONDS", 0.1)
    monkeypatch.setattr(activities, "TICK_SECONDS", 0.05)

    location = await ActivityEnvironment().run(get_location, MOCKED_IP, True)

    assert location == activities.JOB_RESULT
    assert mocked_network.calls.call_count == 0
