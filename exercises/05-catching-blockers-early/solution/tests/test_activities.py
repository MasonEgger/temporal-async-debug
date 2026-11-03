"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the audit trail; test_probe_all_activities.py covers the event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from activities import _archive_audit_trail, get_ip, get_location
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
