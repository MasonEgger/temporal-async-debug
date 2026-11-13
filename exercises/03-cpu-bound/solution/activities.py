"""ABOUTME: The geo-enrichment activities: get_location is a plain def with a CPU-bound transform.
ABOUTME: Exercise 03 (03-cpu-bound) copy: get_location runs on the worker's activity_executor.

get_location is a plain ``def`` function, so the worker runs it on its ``activity_executor``, a
thread pool, and its CPU-bound transform runs on a pool thread instead of the event loop. get_ip
stays ``async def`` over ``httpx.AsyncClient``; it does no CPU work.
Each activity fetches from a short round-robin list of providers and falls back to the next on
failure. get_location then derives a short tag from the location by repeated hashing. The number of
rounds comes from the workflow input and bounds the work: a run pins one core for a fixed amount of
computation and then returns.
The pool thread still holds the GIL while it hashes, so the process stays near 100 percent CPU; only
more Worker processes add CPU parallelism.
"""

from __future__ import annotations

import hashlib
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


def _stretch_digest(seed: str, rounds: int) -> str:
    """Derive a hex digest from the seed by hashing it ``rounds`` times in a row.

    This is the exercise's CPU-bound transform: each round feeds the previous digest back into
    SHA-256, a short pure-Python loop that holds the GIL for as long as it runs. The work is bounded
    by ``rounds``, never by a clock.

    Args:
        seed: The text to start from, for example the location line a provider returned.
        rounds: How many times to hash. Zero returns the seed's own digest.

    Returns:
        The final digest as a hex string.
    """
    digest = hashlib.sha256(seed.encode()).digest()
    for _ in range(rounds):
        digest = hashlib.sha256(digest).digest()
    return digest.hex()


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
def get_location(ip: str, work_rounds: int) -> str:
    """Look up where an IP address lives, from the first geo provider that answers, and tag it.

    Args:
        ip: Address to look up, as returned by get_ip.
        work_rounds: How many hashing rounds the tagging transform runs, for example
            HEALTHY_WORK_ROUNDS for a healthy run.

    Returns:
        The city, region, and country of the address as one comma-separated line, followed by an
        eight-character tag in parentheses.

    Raises:
        RuntimeError: If every provider fails.
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
            tag = _stretch_digest(location, work_rounds)[:8]
            return f"{location} ({tag})"
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
