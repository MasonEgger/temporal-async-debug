"""ABOUTME: The geo-enrichment activities, async def over httpx, with the archiving moved off the loop.
ABOUTME: Exercise 05 (05-catching-blockers-early) copy: get_location awaits the audit trail on a thread.

Both activities are ``async def`` functions, so the worker runs them on its one event loop. The
audit-trail archiving at the top of get_location runs on a thread through ``asyncio.to_thread``
instead, so the loop stays live while it works. The work is mostly one big ``zlib.compress`` call,
which releases the GIL, so the thread and the loop run side by side.
Each activity fetches from a short round-robin list of providers and falls back to the next on
failure. get_location first archives an audit trail for the lookup: it builds a realistic
audit trail (seeded JSON lines, cached at import) and compresses it with zlib. The number of
records comes from the workflow input and bounds the work, a few hundred milliseconds on every run,
and then the lookup carries on.
Nothing times out and nothing fails, and with the work off the loop nothing else waits either.
The regression guard is tests/test_probe_all_activities.py, which runs every ``async def`` activity
registered on the worker under a 50 ms probe and fails if any of them holds the loop.
"""

from __future__ import annotations

import asyncio
import functools
import json
import random
import zlib
from typing import TYPE_CHECKING

import httpx
from shared import PAYLOAD_RECORDS
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


TRAIL_SEED: int = 20260101
"""Seed for the audit-trail generator, so every Worker builds the same bytes."""

COMPRESSION_LEVEL: int = 9
"""zlib's slowest, tightest level, so the compression dominates the cost of archiving."""

_ACTIONS: tuple[str, ...] = ("login", "logout", "read", "create", "update", "delete", "export", "search")
_STATUSES: tuple[int, ...] = (200, 200, 200, 200, 201, 204, 301, 400, 401, 403, 404, 500)
_EPOCH_START: int = 1_767_225_600  # 2026-01-01T00:00:00Z


def build_audit_trail(records: int, seed: int = TRAIL_SEED) -> bytes:
    """Build ``records`` audit-log lines as UTF-8 JSON lines, the same bytes for the same seed.

    Each line carries a timestamp, a request id, a client IP, an action, a status, and a latency in
    milliseconds. The timestamps climb, the request ids are hex, and the actions, statuses, and clients
    repeat, so the trail compresses the way real logs do.

    Args:
        records: How many lines to generate.
        seed: Seed for the random generator.

    Returns:
        The lines joined by newlines, with a trailing newline when there is at least one.
    """
    rng = random.Random(seed)
    clients = [f"10.{rng.randrange(256)}.{rng.randrange(256)}.{rng.randrange(1, 255)}" for _ in range(200)]
    timestamp = _EPOCH_START
    lines: list[str] = []
    for _ in range(records):
        timestamp += rng.randrange(0, 3)
        entry = {
            "ts": timestamp,
            "request_id": f"{rng.getrandbits(64):016x}",
            "client_ip": rng.choice(clients),
            "action": rng.choice(_ACTIONS),
            "status": rng.choice(_STATUSES),
            "latency_ms": round(rng.lognormvariate(3.5, 0.8), 1),
        }
        lines.append(json.dumps(entry, separators=(",", ":")))
    return "".join(f"{line}\n" for line in lines).encode()


@functools.cache
def _audit_trail(records: int) -> bytes:
    """Return the audit trail for ``records`` lines, built once per size and then reused.

    The trail is built in the Worker and never crosses a Temporal boundary, so only the record count
    travels in the Workflow input. It is built once at import for PAYLOAD_RECORDS, so the per-call cost
    of archiving is the compression that follows and nothing else.
    """
    return build_audit_trail(records)


_audit_trail(PAYLOAD_RECORDS)  # prebuilt at import so no call pays for it


def _archive_audit_trail(ip: str, records: int) -> int:
    """Compress the audit trail for the lookup with zlib and discard the result.

    A real archiver would upload the compressed bytes and return a key for them. This one throws the
    bytes away, because the compression is the point.
    This is the exercise's short blocker: synchronous, bounded by ``records`` and never by a clock.
    Nearly all of the time goes to one large ``zlib.compress`` call, which releases the GIL while it
    works, so run on a thread it leaves the loop free to run.

    Args:
        ip: The address the archive is labeled for. It does not change the bytes compressed.
        records: How many audit records to archive.

    Returns:
        How many records went into the archive.
    """
    trail = _audit_trail(records)
    zlib.compress(trail, COMPRESSION_LEVEL)
    return records


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
async def get_location(ip: str, payload_records: int) -> str:
    """Archive an audit trail for the lookup, then look up where an IP address lives.

    Args:
        ip: Address to look up, as returned by get_ip.
        payload_records: How many audit records to archive, for example PAYLOAD_RECORDS.

    Returns:
        The city, region, and country of the address as one comma-separated line, followed by the
        number of audit records archived in parentheses.

    Raises:
        RuntimeError: If every provider fails.
    """
    # Awaiting a thread is safe here only because this work is short and bounded: a few hundred
    # milliseconds, no heartbeat_timeout. A thread cannot be cancelled, so long work that must stop on
    # cancel needs a def activity with heartbeats instead (see exercise 04).
    archived = await asyncio.to_thread(_archive_audit_trail, ip, payload_records)
    errors: list[str] = []
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
            return f"{location} ({archived} audit records)"
    raise RuntimeError(f"every geo provider failed: {'; '.join(errors)}")
