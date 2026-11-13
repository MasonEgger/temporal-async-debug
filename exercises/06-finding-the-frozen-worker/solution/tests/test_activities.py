"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the location cache; test_probe.py covers the event loop.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

from activities import get_ip, get_location
from conftest import MOCKED_IP, MOCKED_LOCATION
from db_lock import LOCATIONS_SCHEMA
from temporalio.testing import ActivityEnvironment

if TYPE_CHECKING:
    from pathlib import Path

    import respx

CACHED_LOCATION: str = "Example City, Example Region, Example Country"
"""Location the test writes into the cache, distinct from what the mocked providers answer."""


def _create_cache(directory: Path, rows: list[tuple[str, str]]) -> Path:
    """Create a location cache database under directory holding the given (ip, location) rows."""
    database_path = directory / "location-cache.sqlite3"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(LOCATIONS_SCHEMA)
        connection.executemany("INSERT INTO locations (ip, location) VALUES (?, ?)", rows)
    return database_path


async def test_get_ip_returns_the_stripped_address(mocked_network: respx.MockRouter) -> None:
    """get_ip returns the first provider's body without its trailing newline."""
    assert await ActivityEnvironment().run(get_ip) == MOCKED_IP
    assert mocked_network.calls.call_count == 1


def test_get_location_asks_the_providers_when_there_is_no_cache(mocked_network: respx.MockRouter) -> None:
    """With no cache path, get_location asks the first geo provider and parses its payload."""
    assert ActivityEnvironment().run(get_location, MOCKED_IP, None) == MOCKED_LOCATION
    assert mocked_network.calls.call_count == 1


def test_get_location_returns_a_cache_hit_without_asking_the_providers(
    mocked_network: respx.MockRouter, tmp_path: Path
) -> None:
    """A cached row is the answer, and no HTTP request goes out."""
    database_path = _create_cache(tmp_path, [(MOCKED_IP, CACHED_LOCATION)])

    location = ActivityEnvironment().run(get_location, MOCKED_IP, str(database_path))

    assert location == CACHED_LOCATION
    assert mocked_network.calls.call_count == 0


def test_get_location_falls_through_to_the_providers_on_a_cache_miss(
    mocked_network: respx.MockRouter, tmp_path: Path
) -> None:
    """An address the cache does not hold is looked up with the geo providers."""
    database_path = _create_cache(tmp_path, [("198.51.100.20", CACHED_LOCATION)])

    location = ActivityEnvironment().run(get_location, MOCKED_IP, str(database_path))

    assert location == MOCKED_LOCATION
    assert mocked_network.calls.call_count == 1
