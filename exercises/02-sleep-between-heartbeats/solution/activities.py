"""ABOUTME: The geo-enrichment activities, async def over httpx, with a slow-job poll loop in get_location.
ABOUTME: Exercise 02 (02-sleep-between-heartbeats) copy: the poll wait is awaited in ticks, one heartbeat each.

get_location either asks the public geo providers (the healthy runs) or, when ``slow_job`` is set,
polls a simulated slow job until it finishes. Between polls it waits in awaited one-second ticks and
calls ``activity.heartbeat()`` on every tick, so the heartbeats flush on the event loop more often than
the workflow's heartbeat_timeout and a cancellation lands at the await.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import TYPE_CHECKING

import httpx
from temporalio import activity

if TYPE_CHECKING:
    from collections.abc import Callable

HTTP_TIMEOUT_SECONDS: float = 4.0
"""Per-request timeout for the public providers, short enough that a hung lookup does not masquerade as a frozen loop.

httpx applies the value per phase, so a hung connect followed by a hung read still lands well inside
the activity's start_to_close, and five providers at this timeout still fail over inside it too."""

JOB_SECONDS: float = 20.0
"""How long the simulated slow job runs from its first poll before it reports done."""

POLL_INTERVAL_SECONDS: float = 8.0
"""How long get_location waits between polls of the slow job; longer than the 5-second heartbeat_timeout."""

TICK_SECONDS: float = 1.0
"""How long one awaited tick of the poll wait lasts; one heartbeat is recorded per tick."""

JOB_RESULT: str = "Austin, Texas, United States"
"""What the simulated slow job returns once it is done."""

_JOB_STARTED_AT: dict[str, float] = {}
"""Monotonic start time of each workflow run's simulated job, keyed on the workflow run id.

Keying on the run id means a retried attempt polls the same job instead of starting a new one,
so the job finishes on schedule no matter how many attempts have failed."""

IP_PROVIDERS: tuple[str, ...] = (
    "https://icanhazip.com",
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://ident.me",
    "https://checkip.amazonaws.com",
)
"""Plain-text endpoints that each echo back the caller's public IP address."""


def _join_location_fields(response: httpx.Response, city_key: str, region_key: str, country_key: str) -> str:
    """Join a JSON response's city, region, and country fields into one location line.

    Args:
        response: A geo provider's response, expected to carry a JSON object.
        city_key: The provider's key for the city.
        region_key: The provider's key for the region.
        country_key: The provider's key for the country.

    Returns:
        The three fields as one comma-separated line.

    Raises:
        ValueError: If the body is not JSON, not a JSON object, or lacks any of the fields, so the
            caller fails over to the next provider.
    """
    body: object = response.json()
    if not isinstance(body, dict):
        raise ValueError(f"expected a JSON object, got {type(body).__name__}")
    fields = [body.get(key) for key in (city_key, region_key, country_key)]
    if any(field_value is None for field_value in fields):
        raise ValueError(f"missing location fields in {body!r}")
    return ", ".join(str(field_value) for field_value in fields)


def _parse_ipapi_co(response: httpx.Response) -> str:
    """Parse a location string from an ipapi.co JSON response."""
    return _join_location_fields(response, "city", "region", "country_name")


def _parse_ipwho_is(response: httpx.Response) -> str:
    """Parse a location string from an ipwho.is JSON response."""
    return _join_location_fields(response, "city", "region", "country")


def _parse_ip_api_com(response: httpx.Response) -> str:
    """Parse a location string from an ip-api.com JSON response."""
    return _join_location_fields(response, "city", "regionName", "country")


GEO_PROVIDERS: tuple[tuple[str, Callable[[httpx.Response], str]], ...] = (
    ("https://ipapi.co/{ip}/json/", _parse_ipapi_co),
    ("https://ipwho.is/{ip}", _parse_ipwho_is),
    ("http://ip-api.com/json/{ip}", _parse_ip_api_com),
)
"""Geo lookup endpoints paired with the parser for each one's JSON shape."""


def _rotated[ProviderT](providers: tuple[ProviderT, ...]) -> list[ProviderT]:
    """Return the providers rotated to start at a random offset, for simple round-robin spread.

    Args:
        providers: The ordered provider list to rotate.

    Returns:
        The same providers, every one included once, starting at a random position.
    """
    offset = random.randrange(len(providers))
    return [*providers[offset:], *providers[:offset]]


@activity.defn
async def get_ip() -> str:
    """Fetch the worker's public IP address from the first provider that answers.

    Returns:
        The public IP address, stripped of the provider's trailing whitespace.

    Raises:
        RuntimeError: If every provider fails.
    """
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url in _rotated(IP_PROVIDERS):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text.strip()
            except httpx.HTTPError as error:
                errors.append(f"{url}: {error!r}")
    raise RuntimeError(f"every IP provider failed: {'; '.join(errors)}")


def _job_is_done(run_id: str, attempt: int, poll_number: int) -> bool:
    """Poll the simulated slow job for this workflow run, starting it on the first poll.

    Args:
        run_id: The workflow run id the job is keyed on.
        attempt: The activity attempt making the poll, printed so a dead attempt's polls are visible.
        poll_number: Which poll this is within the attempt, printed with the job's progress.

    Returns:
        True once JOB_SECONDS have passed since the run's first poll.
    """
    now = time.monotonic()
    elapsed = now - _JOB_STARTED_AT.setdefault(run_id, now)
    print(
        f"[attempt {attempt}] poll {poll_number}: job {min(elapsed, JOB_SECONDS):.0f}s of {JOB_SECONDS:.0f}s",
        flush=True,
    )
    return elapsed >= JOB_SECONDS


@activity.defn
async def get_location(ip: str, slow_job: bool) -> str:
    """Look up where an IP address lives, from a slow job or the first geo provider that answers.

    Args:
        ip: Address to look up, as returned by get_ip.
        slow_job: True to poll the simulated slow job instead of asking the public providers.

    Returns:
        The city, region, and country of the address, as one comma-separated line.

    Raises:
        RuntimeError: If every provider fails.
    """
    if slow_job:
        info = activity.info()
        poll_number = 0
        while True:
            poll_number += 1
            if _job_is_done(f"{info.workflow_id}/{info.workflow_run_id}", info.attempt, poll_number):
                return JOB_RESULT
            loop = asyncio.get_running_loop()
            next_poll_at = loop.time() + POLL_INTERVAL_SECONDS
            while (remaining := next_poll_at - loop.time()) > 0:
                if activity.in_activity():
                    activity.heartbeat()
                await asyncio.sleep(min(TICK_SECONDS, remaining))

    errors: list[str] = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url_template, parse in _rotated(GEO_PROVIDERS):
            url = url_template.format(ip=ip)
            try:
                response = await client.get(url)
                response.raise_for_status()
                return parse(response)
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{url}: {error!r}")
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
