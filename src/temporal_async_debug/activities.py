"""ABOUTME: The demo's two async activities, each able to block the worker's event loop on purpose.
ABOUTME: get_ip and get_location heartbeat, apply their delay mode, then make one httpx GET apiece.

The Temporal Python worker runs its poller, its heartbeat sender, and every ``async def`` activity
on one asyncio event loop. Both activities below take a ``mode`` that decides how they wait:

- ``"block"`` calls ``time.sleep``, which stops that entire loop. This is the deliberate bug the
  tutorial diagnoses, and the reader is meant to look at the line and see nothing wrong with it.
- ``"slow"`` awaits ``asyncio.sleep`` in short steps and heartbeats between them, which delays this
  activity and nothing else while it keeps one of the worker's activity slots for the whole duration.

``HEALTHY_EQUIVALENTS`` names the correct calls in one place so the tutorial can point at the
contrast without hunting through the file.
"""

from __future__ import annotations

import asyncio
import time

import httpx
from temporalio import activity

HEALTHY_EQUIVALENTS: tuple[str, ...] = ("asyncio.sleep", "httpx")
"""The non-blocking calls an async activity should reach for: ``asyncio.sleep`` in place of
``time.sleep``, and ``httpx``'s async client in place of a synchronous HTTP library."""

IP_LOOKUP_URL: str = "https://icanhazip.com"
"""Plain-text endpoint that echoes back the caller's public IP address."""

GEO_LOOKUP_URL_TEMPLATE: str = "https://ipapi.co/{ip}/json/"
"""Geo lookup endpoint, formatted with the address that get_ip returned."""

HTTP_TIMEOUT_SECONDS: float = 10.0
"""Per-request timeout, short enough that a hung lookup does not masquerade as a frozen loop."""

SLOW_HEARTBEAT_INTERVAL_SECONDS: float = 3.0
"""How often slow mode heartbeats while it waits. It sits well inside the workflow's 10 second
heartbeat_timeout, so the slow activity keeps reporting progress and holds its slot for the full
delay instead of being cancelled. Temporal's guidance is to heartbeat a long-running activity at
an interval a few times shorter than the heartbeat timeout."""


async def _apply_mode(mode: str, block_seconds: float) -> None:
    """Wait for block_seconds in whichever way the mode asks for.

    Both activities call this before their HTTP request, so a single mode flag decides
    whether the worker's event loop keeps running during the wait.

    Block mode never heartbeats, on purpose: the frozen loop cannot, which is what lets the
    workflow's short heartbeat_timeout catch it. Slow mode heartbeats between short sleeps so it
    holds its activity slot for the whole delay, which is what makes the slot-exhaustion lesson bite.

    Args:
        mode: "block" to wait with time.sleep, "slow" to await asyncio.sleep in heartbeated steps.
            Any other value waits not at all.
        block_seconds: Seconds to wait. Zero, the healthy default, applies no delay.
    """
    if block_seconds <= 0:
        return
    if mode == "block":
        # ANTIPATTERN (deliberate, for teaching): time.sleep blocks the single worker event loop,
        # starving the poller, heartbeat sender, and every other async activity. Correct: await
        # asyncio.sleep for cooperative delay, or run truly blocking work in an executor. Do not copy.
        time.sleep(block_seconds)
    elif mode == "slow":
        elapsed = 0.0
        while elapsed < block_seconds:
            step = min(SLOW_HEARTBEAT_INTERVAL_SECONDS, block_seconds - elapsed)
            await asyncio.sleep(step)
            elapsed += step
            # Heartbeat only inside a real activity; the starvation-probe test calls this bare.
            if activity.in_activity():
                activity.heartbeat("slow mode holding the activity slot")


@activity.defn
async def get_ip(block_seconds: float, mode: str) -> str:
    """Fetch the worker's public IP address.

    The heartbeat comes first on purpose: with a short heartbeat_timeout on the workflow side,
    a run that blocks the loop stops heartbeating and the server times the activity out.

    Args:
        block_seconds: Seconds to wait before the request. Zero means no wait.
        mode: "block" or "slow"; see _apply_mode.

    Returns:
        The public IP address, stripped of the endpoint's trailing newline.
    """
    activity.heartbeat("fetching ip")
    await _apply_mode(mode, block_seconds)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(IP_LOOKUP_URL)
    response.raise_for_status()
    return response.text.strip()


@activity.defn
async def get_location(ip: str, block_seconds: float, mode: str) -> str:
    """Look up where an IP address lives.

    Args:
        ip: Address to look up, as returned by get_ip.
        block_seconds: Seconds to wait before the request. Zero means no wait.
        mode: "block" or "slow"; see _apply_mode.

    Returns:
        The city, region, and country of the address, as one comma-separated line.
    """
    activity.heartbeat("fetching location")
    await _apply_mode(mode, block_seconds)
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(GEO_LOOKUP_URL_TEMPLATE.format(ip=ip))
    response.raise_for_status()
    location = response.json()
    return f"{location['city']}, {location['region']}, {location['country_name']}"
