"""ABOUTME: The geo-enrichment activities: get_location reads a SQLite location cache, then the geo providers.
ABOUTME: Exercise 06 (06-finding-the-frozen-worker) copy: get_location is a plain def on the activity_executor.

get_location is a plain ``def`` function, so the worker runs it on its ``activity_executor``, a
thread pool. Its ``sqlite3`` lookup is a synchronous database call: when another connection holds
the cache's lock, the lookup's ``SELECT`` waits for it, and that wait blocks one pool thread
instead of the event loop. get_ip stays ``async def`` over ``httpx.AsyncClient``; it does no
blocking work.

When ``location_cache_path`` is set, get_location looks the address up in the cache first, and on a
miss it asks the geo providers. Each activity fetches from a short round-robin list of providers and
falls back to the next on failure.
"""

from __future__ import annotations

import random
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import httpx
from temporalio import activity

if TYPE_CHECKING:
    from collections.abc import Callable

HTTP_TIMEOUT_SECONDS: float = 4.0
"""Per-request timeout for the public providers, short enough that a hung lookup does not masquerade as a frozen loop.

httpx applies the value per phase, so a hung connect followed by a hung read still lands well inside
the activity's start_to_close, and five providers at this timeout still fail over inside it too."""

LOCK_WAIT_TIMEOUT_SECONDS: float = 120.0
"""How long the cache lookup waits on a locked database before sqlite3 raises ``database is locked``.

It is longer than the exercise's lock hold, so the lookup waits the lock out where a shorter timeout
would raise. It also matches the geo activities' 120-second start_to_close."""

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


def _cached_location(location_cache_path: str, ip: str) -> str | None:
    """Look an IP address up in the location cache, waiting on the cache's lock if another connection holds it.

    Args:
        location_cache_path: Path of the SQLite location cache.
        ip: Address to look up.

    Returns:
        The cached location line, or None when the cache holds no row for the address.
    """
    with closing(sqlite3.connect(location_cache_path, timeout=LOCK_WAIT_TIMEOUT_SECONDS)) as connection:
        row: tuple[str] | None = connection.execute("SELECT location FROM locations WHERE ip = ?", (ip,)).fetchone()
    return None if row is None else row[0]


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
def get_location(ip: str, location_cache_path: str | None) -> str:
    """Look up where an IP address lives, from the location cache first and then the geo providers.

    Args:
        ip: Address to look up, as returned by get_ip.
        location_cache_path: Path of the SQLite location cache to read first, or None to ask the
            geo providers directly.

    Returns:
        The city, region, and country of the address, as one comma-separated line.

    Raises:
        RuntimeError: If the cache has no row for the address and every provider fails.
    """
    # A cache hit is the answer; a miss, or no cache at all, falls through to the providers.
    if location_cache_path is not None:
        cached = _cached_location(location_cache_path, ip)
        if cached is not None:
            return cached

    errors: list[str] = []
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url_template, parse in _rotated(GEO_PROVIDERS):
            url = url_template.format(ip=ip)
            try:
                response = client.get(url)
                response.raise_for_status()
                return parse(response)
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{url}: {error!r}")
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
