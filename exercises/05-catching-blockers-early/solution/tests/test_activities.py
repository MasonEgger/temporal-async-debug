"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the audit trail; test_probe_all_activities.py covers the event loop.
"""

from __future__ import annotations

import json
import zlib
from typing import TYPE_CHECKING

from activities import _archive_audit_trail, build_audit_trail, get_ip, get_location
from conftest import MOCKED_IP, MOCKED_LOCATION
from temporalio.testing import ActivityEnvironment

if TYPE_CHECKING:
    import respx

TINY_PAYLOAD_RECORDS: int = 10
"""A payload small enough that the archiving is instant."""


async def test_get_ip_returns_the_stripped_address(mocked_network: respx.MockRouter) -> None:
    """get_ip returns the first provider's body without its trailing newline."""
    assert await ActivityEnvironment().run(get_ip) == MOCKED_IP
    assert mocked_network.calls.call_count == 1


async def test_get_location_reports_the_location_and_the_archived_records(mocked_network: respx.MockRouter) -> None:
    """get_location asks the first public provider and appends how many audit records it archived."""
    result = await ActivityEnvironment().run(get_location, MOCKED_IP, TINY_PAYLOAD_RECORDS)
    assert result == f"{MOCKED_LOCATION} ({TINY_PAYLOAD_RECORDS} audit records)"
    assert mocked_network.calls.call_count == 1


def test_archive_audit_trail_reports_every_record() -> None:
    """The archive reports how many records went in, including none."""
    assert _archive_audit_trail(MOCKED_IP, 0) == 0
    assert _archive_audit_trail(MOCKED_IP, 1_234) == 1_234


TRAIL_FIELDS: set[str] = {"ts", "request_id", "client_ip", "action", "status", "latency_ms"}
"""The keys every audit-log line carries."""

SMALL_TRAIL_RECORDS: int = 500
"""A trail small enough to build and compress instantly in a test."""


def test_every_trail_line_is_json_with_the_audit_fields() -> None:
    """Each line parses as a JSON object with the six audit fields."""
    lines = build_audit_trail(SMALL_TRAIL_RECORDS).decode().splitlines()
    for line in lines:
        entry = json.loads(line)
        assert set(entry) == TRAIL_FIELDS
        assert isinstance(entry["latency_ms"], float)


def test_trail_line_count_matches_the_requested_records() -> None:
    """The trail has one line per requested record, and none for zero."""
    assert len(build_audit_trail(SMALL_TRAIL_RECORDS).splitlines()) == SMALL_TRAIL_RECORDS
    assert build_audit_trail(0) == b""


def test_trail_is_deterministic_for_a_seed() -> None:
    """The same seed gives the same bytes, and a different seed gives different ones."""
    assert build_audit_trail(SMALL_TRAIL_RECORDS, seed=7) == build_audit_trail(SMALL_TRAIL_RECORDS, seed=7)
    assert build_audit_trail(SMALL_TRAIL_RECORDS, seed=7) != build_audit_trail(SMALL_TRAIL_RECORDS, seed=8)


def test_trail_compresses_like_a_real_log() -> None:
    """The compressed trail is well under half the raw size, unlike random bytes."""
    trail = build_audit_trail(SMALL_TRAIL_RECORDS)
    assert len(zlib.compress(trail, 9)) < len(trail) / 2
