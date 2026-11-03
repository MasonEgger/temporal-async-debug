"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the progress lines; test_cancel_stops_work.py covers cancellation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from activities import get_ip, get_location
from conftest import MOCKED_IP, MOCKED_LOCATION
from temporalio.testing import ActivityEnvironment

if TYPE_CHECKING:
    import respx

TINY_STEPS: int = 3
"""A step count small enough that the work is quick once STEP_SECONDS is patched down."""


@pytest.fixture(autouse=True)
def quick_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink each step from half a second to a few milliseconds."""
    monkeypatch.setattr("activities.STEP_SECONDS", 0.001)


async def test_get_ip_returns_the_stripped_address(mocked_network: respx.MockRouter) -> None:
    """get_ip returns the first provider's body without its trailing newline."""
    assert await ActivityEnvironment().run(get_ip) == MOCKED_IP
    assert mocked_network.calls.call_count == 1


def test_get_location_returns_the_location_and_step_count(mocked_network: respx.MockRouter) -> None:
    """get_location asks the first public provider and appends the step count it ran."""
    result = ActivityEnvironment().run(get_location, MOCKED_IP, TINY_STEPS)
    assert result == f"{MOCKED_LOCATION} ({TINY_STEPS} steps)"
    assert mocked_network.calls.call_count == 1


def test_get_location_prints_one_flushed_progress_line_per_step(
    mocked_network: respx.MockRouter, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each step prints a line carrying the attempt number, which is how the Worker log tells attempts apart."""
    ActivityEnvironment().run(get_location, MOCKED_IP, TINY_STEPS)
    lines = capsys.readouterr().out.splitlines()
    assert lines == [f"attempt 1: step {step}/{TINY_STEPS} for {MOCKED_LOCATION}" for step in range(1, TINY_STEPS + 1)]
    assert mocked_network.calls.call_count == 1
