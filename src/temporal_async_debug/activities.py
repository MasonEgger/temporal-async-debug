"""ABOUTME: The geo-enrichment activities, each able to block the worker's event loop on purpose.
ABOUTME: get_ip and get_location apply their delay mode, then fetch from a round-robin provider list.

The Temporal Python worker runs its poller and every ``async def`` activity on one asyncio event
loop. Both activities below take a ``mode`` (one of ``shared.VALID_MODES``) that decides how they
wait; see ``_apply_mode`` for what each mode does. The modes fall into two families:

- Freezing modes (``"block"``, ``"cpu"``) stop that entire loop. These are the deliberate bugs
  the tutorial diagnoses, and the reader is meant to look at the line and see nothing wrong with
  it.
- Cooperative modes (``"slow"``, ``"slow_heartbeat"``, ``"stuck_no_heartbeat"``) await
  ``asyncio.sleep`` instead, delaying this activity and nothing else, though a running activity
  keeps its slot until it returns, so each still holds one of the worker's slots for the whole
  delay.

Each activity fetches from a short round-robin list of providers and falls back to the next on
failure, so one provider's rate limit or outage does not break the demo. ``HEALTHY_EQUIVALENTS``
names the correct calls in one place so the tutorial can point at the contrast.
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

HEALTHY_EQUIVALENTS: tuple[str, ...] = ("asyncio.sleep", "httpx")
"""The non-blocking calls an async activity should reach for: ``asyncio.sleep`` in place of
``time.sleep``, and ``httpx``'s async client in place of a synchronous HTTP library."""

HEARTBEAT_STEP_SECONDS: float = 3.0
"""Interval between heartbeats in slow_heartbeat mode, well under any heartbeat_timeout the
workflow sets for that mode."""

HTTP_TIMEOUT_SECONDS: float = 10.0
"""Per-request timeout, short enough that a hung lookup does not masquerade as a frozen loop."""

IP_PROVIDERS: tuple[str, ...] = (
    "https://icanhazip.com",
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://ident.me",
    "https://checkip.amazonaws.com",
)
"""Plain-text endpoints that each echo back the caller's public IP address."""


def _parse_ipapi_co(response: httpx.Response) -> str:
    """Parse a location string from an ipapi.co JSON response."""
    body: dict[str, object] = response.json()
    return f"{body['city']}, {body['region']}, {body['country_name']}"


def _parse_ipwho_is(response: httpx.Response) -> str:
    """Parse a location string from an ipwho.is JSON response."""
    body: dict[str, object] = response.json()
    return f"{body['city']}, {body['region']}, {body['country']}"


def _parse_ip_api_com(response: httpx.Response) -> str:
    """Parse a location string from an ip-api.com JSON response."""
    body: dict[str, object] = response.json()
    return f"{body['city']}, {body['regionName']}, {body['country']}"


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


async def _apply_mode(mode: str, block_seconds: float) -> None:
    """Wait for block_seconds in whichever way the mode asks for.

    Both activities call this before their HTTP request, so a single mode flag decides
    whether the worker's event loop keeps running during the wait, and whether the
    activity heartbeats while it waits.

    Args:
        mode: One of shared.VALID_MODES. "block" waits with time.sleep, freezing the
            event loop. "cpu" spins on time.monotonic, also freezing the loop but pinning
            the GIL instead of releasing it. "slow" awaits asyncio.sleep once, cooperative
            but silent. "slow_heartbeat" awaits asyncio.sleep in steps and heartbeats
            between them, the correct way to hold a slot for legitimate long work.
            "stuck_no_heartbeat" awaits asyncio.sleep once like "slow" but never
            heartbeats, tripping a heartbeat_timeout the workflow sets for it. Any other
            value waits not at all.
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
    elif mode == "slow":
        await asyncio.sleep(block_seconds)
    elif mode == "slow_heartbeat":
        remaining = block_seconds
        while remaining > 0:
            step = min(HEARTBEAT_STEP_SECONDS, remaining)
            await asyncio.sleep(step)
            remaining -= step
            if activity.in_activity():
                activity.heartbeat("slow_heartbeat progress")
    elif mode == "stuck_no_heartbeat":
        # ANTIPATTERN (deliberate, for teaching): this awaits long-running work but never
        # heartbeats, so a workflow that sets heartbeat_timeout has the server cancel it
        # mid-flight. Correct: heartbeat periodically during long work, as slow_heartbeat does.
        # Do not copy.
        await asyncio.sleep(block_seconds)


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
    await _apply_mode(mode, block_seconds)
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
    await _apply_mode(mode, block_seconds)
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for url_template, parse in _rotated(GEO_PROVIDERS):
            url = url_template.format(ip=ip)
            try:
                response = await client.get(url)
                response.raise_for_status()
                return parse(response)
            except (httpx.HTTPError, KeyError, ValueError) as error:
                errors.append(f"{url}: {error!r}")
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
