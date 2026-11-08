"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the slow-job routing; test_heartbeat.py covers the heartbeats.
"""

from __future__ import annotations

import asyncio
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


async def test_the_status_check_observes_the_same_job_across_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """A retried attempt polls the job its first attempt started, because the job is keyed on the run id."""
    monkeypatch.setattr(activities, "JOB_SECONDS", 0.1)
    monkeypatch.setattr(activities, "_JOB_STARTED_AT", {})
    run_key = "geo-workflow/run-1"

    first_attempt_done = await activities._job_is_done(run_key, attempt=1, poll_number=1)  # noqa: SLF001
    await asyncio.sleep(0.15)
    second_attempt_done = await activities._job_is_done(run_key, attempt=2, poll_number=1)  # noqa: SLF001
    other_run_done = await activities._job_is_done("geo-workflow/run-2", attempt=1, poll_number=1)  # noqa: SLF001

    assert not first_attempt_done
    assert second_attempt_done
    assert not other_run_done
    assert sorted(activities._JOB_STARTED_AT) == [run_key, "geo-workflow/run-2"]  # noqa: SLF001


async def test_the_status_check_yields_to_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The awaited status check hands control back to the loop, so a parked task runs during it."""
    monkeypatch.setattr(activities, "_JOB_STARTED_AT", {})
    ran_during_check = False

    async def parked_task() -> None:
        nonlocal ran_during_check
        ran_during_check = True

    parked = asyncio.create_task(parked_task())
    await activities._job_is_done("geo-workflow/run-3", attempt=1, poll_number=1)  # noqa: SLF001
    ran_before_awaiting_it = ran_during_check
    await parked

    assert ran_before_awaiting_it
