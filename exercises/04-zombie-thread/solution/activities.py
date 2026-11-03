"""ABOUTME: The geo-enrichment activities: get_location is a plain def that heartbeats from its own thread.
ABOUTME: Exercise 04 (04-zombie-thread) copy: a timeout or cancel reaches the work as CancelledError.

get_location is a plain ``def`` function, so the worker runs it on its ``activity_executor``, a thread
pool, and it heartbeats between steps from that same thread. A timeout or cancel is delivered through the
heartbeat as ``temporalio.exceptions.CancelledError`` raised inside the thread, so the work stops instead of
finishing after its attempt failed. get_ip stays ``async def`` over ``httpx.AsyncClient``; it does no
blocking work.
Each activity fetches from a short round-robin list of providers and falls back to the next on failure.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

import httpx
from temporalio import activity
from temporalio.exceptions import CancelledError

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

    Each line carries the attempt number and is flushed at once. After every step the work
    heartbeats from its own thread, which is where a timeout or cancel is delivered: the SDK raises
    ``temporalio.exceptions.CancelledError`` in this thread and the loop ends.

    Args:
        location: The location line a provider returned.
        steps: How many steps to run.
        attempt: The activity attempt that started this work, for the progress lines.

    Returns:
        The location followed by the step count in parentheses.

    Raises:
        temporalio.exceptions.CancelledError: If the attempt was cancelled or timed out, re-raised
            after one log line so the activity still appears cancelled.
    """
    step = 0
    try:
        for step in range(1, steps + 1):
            time.sleep(STEP_SECONDS)
            print(f"attempt {attempt}: step {step}/{steps} for {location}", flush=True)
            if activity.in_activity():
                activity.heartbeat(step)
    except CancelledError:
        print(f"attempt {attempt}: cancelled during step {step}/{steps}, work stopped", flush=True)
        raise
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


@activity.defn
def get_location(ip: str, work_steps: int) -> str:
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
        temporalio.exceptions.CancelledError: If the attempt was cancelled or timed out mid-work.
    """
    errors: list[str] = []
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url_template, parse in _rotated(GEO_PROVIDERS):
            url = url_template.format(ip=ip)
            try:
                response = client.get(url)
                response.raise_for_status()
                location = parse(response)
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{url}: {error!r}")
                continue
            return _blocking_work(location, work_steps, activity.info().attempt)
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
