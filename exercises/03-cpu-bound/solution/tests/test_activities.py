"""ABOUTME: Behavior tests for the geo activities under ActivityEnvironment, with the network mocked.
ABOUTME: They cover the returns and the work_rounds tag; test_probe.py covers the event loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from activities import _stretch_digest, get_ip, get_location
from conftest import MOCKED_IP, MOCKED_LOCATION
from temporalio.testing import ActivityEnvironment

if TYPE_CHECKING:
    import respx

TINY_WORK_ROUNDS: int = 10
"""A work size small enough that the transform is instant."""


async def test_get_ip_returns_the_stripped_address(mocked_network: respx.MockRouter) -> None:
    """get_ip returns the first provider's body without its trailing newline."""
    assert await ActivityEnvironment().run(get_ip) == MOCKED_IP
    assert mocked_network.calls.call_count == 1


def test_get_location_tags_the_provider_location(mocked_network: respx.MockRouter) -> None:
    """get_location asks the first public provider and appends the hashed tag of its location."""
    tag = _stretch_digest(MOCKED_LOCATION, TINY_WORK_ROUNDS)[:8]
    assert ActivityEnvironment().run(get_location, MOCKED_IP, TINY_WORK_ROUNDS) == f"{MOCKED_LOCATION} ({tag})"
    assert mocked_network.calls.call_count == 1


def test_stretch_digest_is_bounded_by_its_round_count() -> None:
    """More rounds change the digest, and the same rounds repeat it, so the work is a fixed count."""
    assert _stretch_digest("seed", 5) == _stretch_digest("seed", 5)
    assert _stretch_digest("seed", 5) != _stretch_digest("seed", 6)
