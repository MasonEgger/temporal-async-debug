"""ABOUTME: The geo-enrichment activities, async def over a synchronous httpx.Client.
ABOUTME: Exercise 01 (01-sync-http-client) copy.

Both activities are ``async def`` functions, so the worker runs them on its one event loop.
Each activity fetches from a short round-robin list of providers and falls back to the next on
failure. get_location takes an optional ``upstream_url``: when set, it asks that one server
instead of the public providers, which is how the bad run reaches the slow endpoint.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import httpx
from temporalio import activity

if TYPE_CHECKING:
    from collections.abc import Callable

HTTP_TIMEOUT_SECONDS: float = 4.0
"""Per-request timeout for the public providers, short enough that a hung lookup does not masquerade as a frozen loop.

httpx applies the value per phase, so a hung connect followed by a hung read still lands well inside
the activity's start_to_close, and five providers at this timeout still fail over inside it too."""

UPSTREAM_TIMEOUT_SECONDS: float = 60.0
"""Per-request timeout for the slow upstream, wide enough that it answers instead of timing out."""

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


# TODO PART C: this activity does blocking I/O. Decide whether it should stay async def.
@activity.defn
async def get_ip() -> str:
    """Fetch the worker's public IP address from the first provider that answers.

    Returns:
        The public IP address, stripped of the provider's trailing whitespace.

    Raises:
        RuntimeError: If every provider fails.
    """
    errors: list[str] = []
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url in _rotated(IP_PROVIDERS):
            try:
                # ANTIPATTERN (deliberate, for teaching): a synchronous client blocks the one event loop while it
                # waits on the socket, so every other task on the worker waits too. Correct: a def Activity on
                # the worker's activity_executor, or an async client. Do not copy.
                response = client.get(url)
                response.raise_for_status()
                return response.text.strip()
            except httpx.HTTPError as error:
                errors.append(f"{url}: {error!r}")
    raise RuntimeError(f"every IP provider failed: {'; '.join(errors)}")


# TODO PART C: this activity does blocking I/O. Decide whether it should stay async def.
@activity.defn
async def get_location(ip: str, upstream_url: str | None) -> str:
    """Look up where an IP address lives, from the first geo provider that answers.

    Args:
        ip: Address to look up, as returned by get_ip.
        upstream_url: Base URL of a single provider to ask instead of the public ones, or None
            to use the public providers.

    Returns:
        The city, region, and country of the address, as one comma-separated line.

    Raises:
        RuntimeError: If every provider fails.
    """
    providers = (
        [(f"{upstream_url}/{{ip}}/json/", _parse_ipapi_co)] if upstream_url is not None else _rotated(GEO_PROVIDERS)
    )
    timeout = HTTP_TIMEOUT_SECONDS if upstream_url is None else UPSTREAM_TIMEOUT_SECONDS
    errors: list[str] = []
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url_template, parse in providers:
            url = url_template.format(ip=ip)
            try:
                # ANTIPATTERN (deliberate, for teaching): a synchronous client blocks the one event loop while it
                # waits on the socket, so every other task on the worker waits too. Correct: a def Activity on
                # the worker's activity_executor, or an async client. Do not copy.
                response = client.get(url, timeout=timeout)
                response.raise_for_status()
                return parse(response)
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{url}: {error!r}")
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
