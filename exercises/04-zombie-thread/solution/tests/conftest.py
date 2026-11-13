"""ABOUTME: Shared pytest fixtures for the exercise copy: a mocked network and pinned provider rotation.
ABOUTME: The cancel test runs the work on a tiny step interval and never touches the network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
import respx
from activities import GEO_PROVIDERS, IP_PROVIDERS

if TYPE_CHECKING:
    from collections.abc import Iterator

MOCKED_IP: str = "203.0.113.7"
"""Address the mocked IP provider returns, from the RFC 5737 documentation range."""

MOCKED_LOCATION: str = "Austin, Texas, United States"
"""Location the mocked geo provider's payload assembles into."""


LOCATION_PAYLOAD: dict[str, str] = {"city": "Austin", "region": "Texas", "country_name": "United States"}
"""Body the first geo provider (ipapi.co) returns for MOCKED_IP."""


@pytest.fixture(autouse=True)
def deterministic_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin provider rotation to start at index 0 so tests know which provider answers first."""
    monkeypatch.setattr("activities.random.randrange", lambda _count: 0)


@pytest.fixture
def mocked_network() -> Iterator[respx.MockRouter]:
    """A respx router with the first IP and geo providers answering successfully."""
    with respx.mock(assert_all_called=False) as router:
        router.get(IP_PROVIDERS[0]).mock(return_value=httpx.Response(200, text=f"{MOCKED_IP}\n"))
        router.get(GEO_PROVIDERS[0][0].format(ip=MOCKED_IP)).mock(
            return_value=httpx.Response(200, json=LOCATION_PAYLOAD)
        )
        yield router
