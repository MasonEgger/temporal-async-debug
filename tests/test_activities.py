"""ABOUTME: Behavior tests for the two misbehaving activities: heartbeat order, mode branching, returns.
ABOUTME: Runs them under ActivityEnvironment with httpx mocked by respx, so no test touches the network.

The delay itself is never really taken: both ``time.sleep`` and ``asyncio.sleep`` are patched to
record the seconds they were handed. That keeps the suite fast and makes the mode branch, which is
the demo's whole point, directly observable.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx
import pytest
import respx
from temporalio.testing import ActivityEnvironment

from temporal_async_debug.activities import (
    GEO_LOOKUP_URL_TEMPLATE,
    IP_LOOKUP_URL,
    get_ip,
    get_location,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

MOCKED_IP: str = "203.0.113.7"
"""Address the mocked icanhazip response returns, from the RFC 5737 documentation range."""

MOCKED_GEO_PAYLOAD: dict[str, str] = {"city": "Austin", "region": "Texas", "country_name": "United States"}
"""Body the mocked geo lookup returns for MOCKED_IP."""

EXPECTED_LOCATION: str = "Austin, Texas, United States"
"""Location string get_location should assemble from MOCKED_GEO_PAYLOAD."""


@dataclass
class ActivityCallRecorder:
    """Ordered record of everything an activity did during one test.

    Attributes:
        events: Heartbeats and HTTP GETs in the order they occurred.
        blocking_sleeps: Seconds passed to the patched time.sleep.
        cooperative_sleeps: Seconds passed to the patched asyncio.sleep.
    """

    events: list[str] = field(default_factory=list)
    blocking_sleeps: list[float] = field(default_factory=list)
    cooperative_sleeps: list[float] = field(default_factory=list)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> ActivityCallRecorder:
    """Patch both sleep calls so they record their delay instead of taking it."""
    call_recorder = ActivityCallRecorder()
    real_asyncio_sleep = asyncio.sleep

    def record_blocking_sleep(delay: float) -> None:
        call_recorder.blocking_sleeps.append(delay)

    async def record_cooperative_sleep(delay: float) -> None:
        call_recorder.cooperative_sleeps.append(delay)
        await real_asyncio_sleep(0)

    monkeypatch.setattr(time, "sleep", record_blocking_sleep)
    monkeypatch.setattr(asyncio, "sleep", record_cooperative_sleep)
    return call_recorder


@pytest.fixture
def activity_environment(recorder: ActivityCallRecorder) -> ActivityEnvironment:
    """An ActivityEnvironment whose heartbeats land in the recorder's event list."""
    environment = ActivityEnvironment()

    def record_heartbeat(*details: object) -> None:
        recorder.events.append(f"heartbeat:{details[0]}")

    environment.on_heartbeat = record_heartbeat
    return environment


@pytest.fixture
def mocked_network() -> Iterator[respx.MockRouter]:
    """A respx router that intercepts every httpx request the activities make."""
    with respx.mock(assert_all_called=False) as router:
        yield router


def _route_ip_lookup(router: respx.MockRouter, recorder: ActivityCallRecorder) -> None:
    """Answer the public-IP GET with MOCKED_IP and record where it fell in the order."""

    def respond(request: httpx.Request) -> httpx.Response:
        recorder.events.append("get:ip")
        return httpx.Response(200, text=f"{MOCKED_IP}\n")

    router.get(IP_LOOKUP_URL).mock(side_effect=respond)


def _route_geo_lookup(router: respx.MockRouter, recorder: ActivityCallRecorder) -> None:
    """Answer the geo GET for MOCKED_IP and record where it fell in the order."""

    def respond(request: httpx.Request) -> httpx.Response:
        recorder.events.append("get:location")
        return httpx.Response(200, json=MOCKED_GEO_PAYLOAD)

    router.get(GEO_LOOKUP_URL_TEMPLATE.format(ip=MOCKED_IP)).mock(side_effect=respond)


async def test_get_ip_heartbeats_once_before_its_http_get(
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """get_ip reports progress before it reaches out, so a frozen run stops heartbeating visibly."""
    _route_ip_lookup(mocked_network, recorder)

    await activity_environment.run(get_ip, 0.0, "block")

    assert recorder.events == ["heartbeat:fetching ip", "get:ip"]


async def test_get_location_heartbeats_once_before_its_http_get(
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """get_location heartbeats before its GET for the same reason get_ip does."""
    _route_geo_lookup(mocked_network, recorder)

    await activity_environment.run(get_location, MOCKED_IP, 0.0, "block")

    assert recorder.events == ["heartbeat:fetching location", "get:location"]


async def test_block_mode_sleeps_with_time_sleep(
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """Block mode hands the full delay to time.sleep, the call that freezes the worker's loop."""
    _route_ip_lookup(mocked_network, recorder)

    await activity_environment.run(get_ip, 30.0, "block")

    assert recorder.blocking_sleeps == [30.0]
    assert recorder.cooperative_sleeps == []


async def test_slow_mode_awaits_asyncio_sleep_and_never_blocks(
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """Slow mode takes the same delay cooperatively, leaving the loop free to run other tasks."""
    _route_ip_lookup(mocked_network, recorder)

    await activity_environment.run(get_ip, 30.0, "slow")

    assert recorder.cooperative_sleeps == [30.0]
    assert recorder.blocking_sleeps == []


@pytest.mark.parametrize("mode", ["block", "slow"])
async def test_zero_block_seconds_applies_no_delay_in_either_mode(
    mode: str,
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """The healthy default delays nothing at all, whichever mode is configured."""
    _route_ip_lookup(mocked_network, recorder)

    await activity_environment.run(get_ip, 0.0, mode)

    assert recorder.blocking_sleeps == []
    assert recorder.cooperative_sleeps == []


async def test_get_ip_returns_the_stripped_response_body(
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """The plain-text body arrives with a trailing newline that must not reach the greeting."""
    _route_ip_lookup(mocked_network, recorder)

    assert await activity_environment.run(get_ip, 0.0, "block") == MOCKED_IP


async def test_get_location_formats_the_geo_payload(
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """get_location turns the lookup's three fields into one human-readable line."""
    _route_geo_lookup(mocked_network, recorder)

    assert await activity_environment.run(get_location, MOCKED_IP, 0.0, "block") == EXPECTED_LOCATION


async def test_slow_mode_runs_both_activities_in_order(
    activity_environment: ActivityEnvironment,
    mocked_network: respx.MockRouter,
    recorder: ActivityCallRecorder,
) -> None:
    """End to end: get_ip feeds get_location, both heartbeat, and both delays stay cooperative."""
    _route_ip_lookup(mocked_network, recorder)
    _route_geo_lookup(mocked_network, recorder)

    ip_address = await activity_environment.run(get_ip, 0.01, "slow")
    location = await activity_environment.run(get_location, ip_address, 0.01, "slow")

    assert ip_address == MOCKED_IP
    assert location == EXPECTED_LOCATION
    assert recorder.events == [
        "heartbeat:fetching ip",
        "get:ip",
        "heartbeat:fetching location",
        "get:location",
    ]
    assert recorder.cooperative_sleeps == [0.01, 0.01]
    assert recorder.blocking_sleeps == []
