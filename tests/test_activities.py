"""ABOUTME: Behavior tests for the geo-enrichment activities: mode branching, returns, and failover.
ABOUTME: Runs them under ActivityEnvironment with every provider mocked by respx, so no test hits the network.

The delay itself is never really taken: both ``time.sleep`` and ``asyncio.sleep`` are patched to
record the seconds they were handed, which keeps the suite fast and makes the mode branch, the
demo's whole point, directly observable. Provider rotation is pinned to start at index 0 so the
tests know which provider answers first.
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

from temporal_async_debug.activities import GEO_PROVIDERS, IP_PROVIDERS, get_ip, get_location
from temporal_async_debug.shared import VALID_MODES

if TYPE_CHECKING:
    from collections.abc import Iterator

MOCKED_IP: str = "203.0.113.7"
"""Address the mocked IP provider returns, from the RFC 5737 documentation range."""

MOCKED_LOCATION: str = "Austin, Texas, United States"
"""Location the mocked geo provider's payload assembles into."""

FIRST_GEO_PAYLOAD: dict[str, str] = {"city": "Austin", "region": "Texas", "country_name": "United States"}
"""Body the first geo provider (ipapi.co) returns for MOCKED_IP."""


@dataclass
class SleepRecorder:
    """Record of the seconds handed to each patched sleep.

    Attributes:
        blocking_sleeps: Seconds passed to the patched time.sleep.
        cooperative_sleeps: Seconds passed to the patched asyncio.sleep.
    """

    blocking_sleeps: list[float] = field(default_factory=list)
    cooperative_sleeps: list[float] = field(default_factory=list)


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> SleepRecorder:
    """Patch both sleep calls so they record their delay instead of taking it."""
    sleep_recorder = SleepRecorder()
    real_asyncio_sleep = asyncio.sleep

    def record_blocking_sleep(delay: float) -> None:
        sleep_recorder.blocking_sleeps.append(delay)

    async def record_cooperative_sleep(delay: float) -> None:
        sleep_recorder.cooperative_sleeps.append(delay)
        await real_asyncio_sleep(0)

    monkeypatch.setattr(time, "sleep", record_blocking_sleep)
    monkeypatch.setattr(asyncio, "sleep", record_cooperative_sleep)
    return sleep_recorder


@pytest.fixture(autouse=True)
def deterministic_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin provider rotation to start at index 0 so tests know which provider answers first."""
    monkeypatch.setattr("temporal_async_debug.activities.random.randrange", lambda _count: 0)


@pytest.fixture
def mocked_network() -> Iterator[respx.MockRouter]:
    """A respx router with the first IP and geo providers answering successfully."""
    with respx.mock(assert_all_called=False) as router:
        router.get(IP_PROVIDERS[0]).mock(return_value=httpx.Response(200, text=f"{MOCKED_IP}\n"))
        first_geo_url = GEO_PROVIDERS[0][0].format(ip=MOCKED_IP)
        router.get(first_geo_url).mock(return_value=httpx.Response(200, json=FIRST_GEO_PAYLOAD))
        yield router


async def test_block_mode_sleeps_with_time_sleep(
    recorder: SleepRecorder,
    mocked_network: respx.MockRouter,
) -> None:
    """Block mode hands the full delay to time.sleep, the call that freezes the worker's loop."""
    await ActivityEnvironment().run(get_ip, 30.0, "block")

    assert recorder.blocking_sleeps == [30.0]
    assert recorder.cooperative_sleeps == []


async def test_slow_mode_awaits_asyncio_sleep(
    recorder: SleepRecorder,
    mocked_network: respx.MockRouter,
) -> None:
    """Slow mode takes the same delay cooperatively, leaving the loop free to run other tasks."""
    await ActivityEnvironment().run(get_ip, 30.0, "slow")

    assert recorder.cooperative_sleeps == [30.0]
    assert recorder.blocking_sleeps == []


@pytest.mark.parametrize("mode", ["block", "slow"])
async def test_zero_block_seconds_applies_no_delay(
    mode: str,
    recorder: SleepRecorder,
    mocked_network: respx.MockRouter,
) -> None:
    """The healthy default delays nothing at all, whichever mode is configured."""
    await ActivityEnvironment().run(get_ip, 0.0, mode)

    assert recorder.blocking_sleeps == []
    assert recorder.cooperative_sleeps == []


async def test_get_ip_returns_the_stripped_address(mocked_network: respx.MockRouter) -> None:
    """The plain-text body arrives with a trailing newline that must not reach the result."""
    assert await ActivityEnvironment().run(get_ip, 0.0, "block") == MOCKED_IP


async def test_get_location_formats_the_geo_payload(mocked_network: respx.MockRouter) -> None:
    """get_location turns the first provider's three fields into one human-readable line."""
    assert await ActivityEnvironment().run(get_location, MOCKED_IP, 0.0, "block") == MOCKED_LOCATION


async def test_get_ip_fails_over_to_the_next_provider() -> None:
    """When the first provider errors, get_ip moves on and returns the next provider's answer."""
    failover_ip = "198.51.100.9"
    with respx.mock(assert_all_called=False) as router:
        router.get(IP_PROVIDERS[0]).mock(return_value=httpx.Response(500))
        router.get(IP_PROVIDERS[1]).mock(return_value=httpx.Response(200, text=f"{failover_ip}\n"))

        assert await ActivityEnvironment().run(get_ip, 0.0, "block") == failover_ip


async def test_get_location_fails_over_when_the_first_payload_is_unusable() -> None:
    """A 200 whose body lacks the expected keys is a failure too; get_location tries the next provider."""
    failover_location = "Denver, Colorado, United States"
    first_geo_url = GEO_PROVIDERS[0][0].format(ip=MOCKED_IP)
    second_geo_url = GEO_PROVIDERS[1][0].format(ip=MOCKED_IP)
    with respx.mock(assert_all_called=False) as router:
        # ipapi.co answers 200 but without the city/region/country_name keys the parser needs.
        router.get(first_geo_url).mock(return_value=httpx.Response(200, json={"error": "reserved range"}))
        # ipwho.is answers with its own valid shape.
        router.get(second_geo_url).mock(
            return_value=httpx.Response(200, json={"city": "Denver", "region": "Colorado", "country": "United States"})
        )

        assert await ActivityEnvironment().run(get_location, MOCKED_IP, 0.0, "block") == failover_location


@pytest.mark.parametrize(
    "unusable_payload",
    [
        ["Austin", "Texas", "United States"],
        {"city": None, "region": "Texas", "country_name": "United States"},
    ],
    ids=["non-dict-body", "null-field"],
)
async def test_get_location_fails_over_on_a_malformed_payload(unusable_payload: object) -> None:
    """A non-dict body or a null field is a parse failure that fails over, not a leaked error or "None"."""
    failover_location = "Denver, Colorado, United States"
    first_geo_url = GEO_PROVIDERS[0][0].format(ip=MOCKED_IP)
    second_geo_url = GEO_PROVIDERS[1][0].format(ip=MOCKED_IP)
    with respx.mock(assert_all_called=False) as router:
        router.get(first_geo_url).mock(return_value=httpx.Response(200, json=unusable_payload))
        router.get(second_geo_url).mock(
            return_value=httpx.Response(200, json={"city": "Denver", "region": "Colorado", "country": "United States"})
        )

        assert await ActivityEnvironment().run(get_location, MOCKED_IP, 0.0, "block") == failover_location


async def test_slow_heartbeat_mode_heartbeats_before_every_provider_attempt() -> None:
    """slow_heartbeat heartbeats right before each provider request, so a slow provider cannot
    run out the heartbeat_timeout while the activity is legitimately busy."""
    events: list[str] = []

    def failing_request(_request: httpx.Request) -> httpx.Response:
        events.append("request")
        return httpx.Response(500)

    def answering_request(_request: httpx.Request) -> httpx.Response:
        events.append("request")
        return httpx.Response(200, text=f"{MOCKED_IP}\n")

    environment = ActivityEnvironment()
    environment.on_heartbeat = lambda *_details: events.append("heartbeat")
    with respx.mock(assert_all_called=False) as router:
        router.get(IP_PROVIDERS[0]).mock(side_effect=failing_request)
        router.get(IP_PROVIDERS[1]).mock(side_effect=answering_request)

        assert await environment.run(get_ip, 0.0, "slow_heartbeat") == MOCKED_IP

    assert events == ["heartbeat", "request", "heartbeat", "request"]


@pytest.mark.parametrize("mode", ["block", "slow", "stuck_no_heartbeat"])
async def test_non_heartbeat_modes_never_heartbeat_around_the_http_phase(
    mode: str,
    mocked_network: respx.MockRouter,
) -> None:
    """Only slow_heartbeat heartbeats; the other modes leave the HTTP phase silent."""
    heartbeats: list[object] = []
    environment = ActivityEnvironment()
    environment.on_heartbeat = lambda *details: heartbeats.append(details)

    await environment.run(get_location, MOCKED_IP, 0.0, mode)

    assert heartbeats == []


async def test_get_ip_raises_when_every_provider_fails() -> None:
    """With every provider erroring, get_ip exhausts the list and raises rather than returning junk."""
    with respx.mock(assert_all_called=False) as router:
        for url in IP_PROVIDERS:
            router.get(url).mock(return_value=httpx.Response(500))

        with pytest.raises(RuntimeError):
            await ActivityEnvironment().run(get_ip, 0.0, "block")


def test_valid_modes_names_every_delay_mode() -> None:
    """VALID_MODES names exactly the five delay modes the demo exercises."""
    assert set(VALID_MODES) == {"block", "cpu", "slow", "slow_heartbeat", "stuck_no_heartbeat"}


async def test_cpu_mode_busy_loops_without_sleeping_or_awaiting(
    recorder: SleepRecorder,
    mocked_network: respx.MockRouter,
) -> None:
    """CPU mode spins on time.monotonic, taking real wall-clock time without sleeping or awaiting."""
    block_seconds = 0.05
    started_at = time.monotonic()

    await ActivityEnvironment().run(get_ip, block_seconds, "cpu")

    elapsed = time.monotonic() - started_at
    assert elapsed >= block_seconds
    assert recorder.blocking_sleeps == []
    assert recorder.cooperative_sleeps == []


async def test_slow_heartbeat_mode_heartbeats_more_than_once(
    recorder: SleepRecorder,
    mocked_network: respx.MockRouter,
) -> None:
    """Slow-heartbeat mode awaits asyncio.sleep in steps and heartbeats after each one."""
    heartbeat_count = 0

    def count_heartbeat(*_details: object) -> None:
        nonlocal heartbeat_count
        heartbeat_count += 1

    environment = ActivityEnvironment()
    environment.on_heartbeat = count_heartbeat

    await environment.run(get_ip, 6.5, "slow_heartbeat")

    assert heartbeat_count >= 2
    assert len(recorder.cooperative_sleeps) >= 2
    assert recorder.blocking_sleeps == []


async def test_slow_heartbeat_mode_returns_result_while_heartbeating(
    mocked_network: respx.MockRouter,
) -> None:
    """slow_heartbeat mode returns the real activity result, proving the mode composes with the
    activity body rather than only with a patched sleep."""
    heartbeat_count = 0

    def count_heartbeat(*_details: object) -> None:
        nonlocal heartbeat_count
        heartbeat_count += 1

    environment = ActivityEnvironment()
    environment.on_heartbeat = count_heartbeat

    result = await environment.run(get_ip, 0.09, "slow_heartbeat")

    assert result == MOCKED_IP
    assert heartbeat_count >= 1


async def test_stuck_no_heartbeat_mode_never_heartbeats(
    recorder: SleepRecorder,
    mocked_network: respx.MockRouter,
) -> None:
    """Stuck-no-heartbeat mode awaits the full delay once and never calls heartbeat."""
    heartbeat_count = 0

    def count_heartbeat(*_details: object) -> None:
        nonlocal heartbeat_count
        heartbeat_count += 1

    environment = ActivityEnvironment()
    environment.on_heartbeat = count_heartbeat

    await environment.run(get_ip, 0.09, "stuck_no_heartbeat")

    assert heartbeat_count == 0
    assert recorder.cooperative_sleeps == [0.09]
    assert recorder.blocking_sleeps == []
