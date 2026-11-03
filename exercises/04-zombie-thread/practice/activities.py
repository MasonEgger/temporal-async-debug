"""ABOUTME: The geo-enrichment activities: get_location is async def and wraps its blocking work in asyncio.to_thread.
ABOUTME: Exercise 04 (04-zombie-thread) copy.

get_location is an ``async def`` function that hands its blocking work to ``asyncio.to_thread``, so the
event loop stays live while the work runs. The work is a loop of short synchronous steps, each of which
sleeps and prints a progress line tagged with the attempt number, so the Worker log shows which attempt's
thread is still running. The workflow gives get_location a heartbeat_timeout, and nothing here
heartbeats, so the server fails an attempt that outlives it and starts the next one.
Each activity fetches from a short round-robin list of providers and falls back to the next on failure.
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

STEP_SECONDS: float = 0.5
"""How long one step of the blocking work sleeps."""

HTTP_TIMEOUT_SECONDS: float = 4.0
"""Per-request timeout for the public providers, short enough that a hung lookup does not masquerade as a frozen loop.

httpx applies the value per phase, so a hung connect followed by a hung read still lands well inside
the activity's start_to_close, and five providers at this timeout still fail over inside it too."""

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


def _blocking_work(location: str, steps: int, attempt: int) -> str:
    """Do the exercise's blocking work: ``steps`` half-second sleeps, one progress line per step.

    Each line carries the attempt number and is flushed at once, so the Worker log shows which
    attempt's thread is still running and when.

    Args:
        location: The location line a provider returned.
        steps: How many steps to run.
        attempt: The activity attempt that started this work, for the progress lines.

    Returns:
        The location followed by the step count in parentheses.
    """
    for step in range(1, steps + 1):
        # TODO PART C: the work never tells the server it is alive, so a timeout or cancel has no way in.
        # Heartbeat once per step here, from this same thread.
        # Also log a line when the cancel arrives, then let it propagate so the work stops.
        time.sleep(STEP_SECONDS)
        print(f"attempt {attempt}: step {step}/{steps} for {location}", flush=True)
    return f"{location} ({steps} steps)"


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


# TODO PART C: this activity wraps its blocking work in asyncio.to_thread. Decide whether it should
# stay async def. If its kind changes, the HTTP client and the call on the request below change with it.
@activity.defn
async def get_location(ip: str, work_steps: int) -> str:
    """Look up where an IP address lives, from the first geo provider that answers, then do the work.

    Args:
        ip: Address to look up, as returned by get_ip.
        work_steps: How many half-second steps the blocking work runs, for example
            HEALTHY_WORK_STEPS for a healthy run.

    Returns:
        The city, region, and country of the address as one comma-separated line, followed by the
        step count in parentheses.

    Raises:
        RuntimeError: If every provider fails.
    """
    errors: list[str] = []
    # TODO PART C: this client and the request call below must match the kind of function you choose.
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url_template, parse in _rotated(GEO_PROVIDERS):
            url = url_template.format(ip=ip)
            try:
                response = await client.get(url)
                response.raise_for_status()
                location = parse(response)
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{url}: {error!r}")
                continue
            # ANTIPATTERN (deliberate, for teaching): cancelling the awaiting coroutine cannot stop a thread that
            # asyncio.to_thread already started, and nothing heartbeats, so when the server times the attempt out the
            # work keeps running and finishes after the attempt failed while the retry runs it again beside it.
            # Correct: a def Activity on the worker's activity_executor that heartbeats from its own thread, so the
            # cancel arrives as CancelledError inside the work. Do not copy.
            # TODO PART C: replace this to_thread call with a direct call once the function is a plain def.
            return await asyncio.to_thread(_blocking_work, location, work_steps, activity.info().attempt)
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
