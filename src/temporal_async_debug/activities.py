"""ABOUTME: The geo-enrichment activities, each able to block the worker's event loop on purpose.
ABOUTME: get_ip and get_location apply their delay mode, then fetch from a round-robin provider list.

The Temporal Python worker runs its poller and every ``async def`` activity on one asyncio event
loop. Both activities below take a ``mode`` (one of ``shared.VALID_MODES``) that decides how they
wait; see ``_apply_mode`` for what each mode does. Both modes freeze that entire loop. These are the
deliberate bugs the tutorial diagnoses, and the reader is meant to look at the line and see nothing
wrong with it.

Each activity fetches from a short round-robin list of providers and falls back to the next on
failure, so one provider's rate limit or outage does not break the demo.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

import httpx
from temporalio import activity

if TYPE_CHECKING:
    from collections.abc import Callable

HTTP_TIMEOUT_SECONDS: float = 4.0
"""Per-request timeout, short enough that a hung lookup does not masquerade as a frozen loop.

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


def _apply_mode(mode: str, block_seconds: float) -> None:
    """Freeze the event loop for block_seconds in whichever way the mode asks for.

    Both activities call this before their HTTP request, so a single mode flag decides how the
    worker's event loop is frozen.

    Args:
        mode: One of shared.VALID_MODES. "block" waits with time.sleep, freezing the event loop.
            "cpu" spins on time.monotonic, also freezing the loop but pinning the GIL instead of
            releasing it. Any other value waits not at all.
        block_seconds: Seconds to wait. Zero, the healthy default, applies no delay.
    """
    if block_seconds <= 0:
        return
    if mode == "block":
        # ANTIPATTERN (deliberate, for teaching): time.sleep blocks the single worker event loop,
        # starving the poller, heartbeat sender, and every other async activity. Correct: await
        # asyncio.sleep for cooperative delay, or run truly blocking work in an executor. Do not copy.
        time.sleep(block_seconds)
    elif mode == "cpu":
        deadline = time.monotonic() + block_seconds
        # ANTIPATTERN (deliberate, for teaching): a CPU-bound loop pins the GIL and freezes the
        # single worker event loop; it is uncancellable so the SDK cannot reclaim the slot.
        # Correct: run CPU-bound work in a ProcessPoolExecutor off the event loop. Do not copy.
        while time.monotonic() < deadline:
            pass


@activity.defn
async def get_ip(block_seconds: float, mode: str) -> str:
    """Fetch the worker's public IP address from the first provider that answers.

    Args:
        block_seconds: Seconds to wait before the request. Zero means no wait.
        mode: One of shared.VALID_MODES; see _apply_mode for what each does.

    Returns:
        The public IP address, stripped of the provider's trailing whitespace.

    Raises:
        RuntimeError: If every provider fails.
    """
    _apply_mode(mode, block_seconds)
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
async def get_location(ip: str, block_seconds: float, mode: str) -> str:
    """Look up where an IP address lives, from the first geo provider that answers.

    Args:
        ip: Address to look up, as returned by get_ip.
        block_seconds: Seconds to wait before the request. Zero means no wait.
        mode: One of shared.VALID_MODES; see _apply_mode for what each does.

    Returns:
        The city, region, and country of the address, as one comma-separated line.

    Raises:
        RuntimeError: If every provider fails.
    """
    _apply_mode(mode, block_seconds)
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
