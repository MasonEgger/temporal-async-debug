"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the upstream_url routing; test_probe.py covers the event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from activities import get_ip, get_location
from conftest import MOCKED_IP, MOCKED_LOCATION
from temporalio.testing import ActivityEnvironment

if TYPE_CHECKING:
    import respx


def test_get_ip_returns_the_stripped_address(mocked_network: respx.MockRouter) -> None:
    """get_ip returns the first provider's body without its trailing newline."""
    assert ActivityEnvironment().run(get_ip) == MOCKED_IP
    assert mocked_network.calls.call_count == 1


def test_get_location_uses_the_public_providers_by_default(mocked_network: respx.MockRouter) -> None:
    """With no upstream URL, get_location asks the first public provider and parses its payload."""
    assert ActivityEnvironment().run(get_location, MOCKED_IP, None) == MOCKED_LOCATION
    assert mocked_network.calls.call_count == 1


def test_get_location_asks_the_upstream_url_when_one_is_given(mocked_network: respx.MockRouter) -> None:
    """An upstream URL replaces the public providers, so the bad run reaches the slow endpoint."""
    upstream_route = mocked_network.get(f"http://127.0.0.1:9/{MOCKED_IP}/json/").mock(
        return_value=httpx.Response(200, json={"city": "Oslo", "region": "Oslo", "country_name": "Norway"})
    )

    location = ActivityEnvironment().run(get_location, MOCKED_IP, "http://127.0.0.1:9")

    assert location == "Oslo, Oslo, Norway"
    assert upstream_route.call_count == 1
