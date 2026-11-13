"""ABOUTME: Tests for db_lock.hold_cache_lock: where the database lives, when the lock is held, when it lets go.
ABOUTME: Every test uses its own tmp_path directory, so no two tests share a database file.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from db_lock import CacheLock, hold_cache_lock

if TYPE_CHECKING:
    from pathlib import Path

SHORT_DELAY_SECONDS: float = 0.3
"""A hold short enough to wait out inside a test."""

LONG_DELAY_SECONDS: float = 30.0
"""A hold far longer than any test waits, so a prompt release cannot come from the delay running out."""

RELEASE_WAIT_SECONDS: float = 5.0
"""How long a second connection waits for the lock before it gives up."""


def _select_locations(database_path: Path, timeout: float) -> list[tuple[str, str]]:
    """Read every row of the locations table through a fresh connection."""
    with closing(sqlite3.connect(database_path, timeout=timeout)) as connection:
        return connection.execute("SELECT ip, location FROM locations").fetchall()


def test_the_database_lives_under_the_directory_and_holds_the_locations_table(tmp_path: Path) -> None:
    """The file sits in the directory passed in, and its locations table has the ip and location columns."""
    with hold_cache_lock(0.0, tmp_path) as lock:
        assert lock.database_path.parent == tmp_path
        assert lock.database_path.is_file()

        # The schema is readable only once the lock lets go, so release it first.
        lock.arm()
        with closing(sqlite3.connect(lock.database_path, timeout=RELEASE_WAIT_SECONDS)) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(locations)")]

    assert columns == ["ip", "location"]


def test_the_lock_is_held_before_arm(tmp_path: Path) -> None:
    """Until arm() is called, a second connection cannot read the table, even waiting past the delay."""
    with hold_cache_lock(SHORT_DELAY_SECONDS, tmp_path) as lock:
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            _select_locations(lock.database_path, timeout=SHORT_DELAY_SECONDS * 2)
        lock.arm()


def test_arm_releases_the_lock_once_the_delay_has_passed(tmp_path: Path) -> None:
    """After arm(), a waiting reader gets in, and not before the delay has run."""
    with hold_cache_lock(SHORT_DELAY_SECONDS, tmp_path) as lock:
        armed_at = time.monotonic()
        lock.arm()
        rows = _select_locations(lock.database_path, timeout=RELEASE_WAIT_SECONDS)
        waited = time.monotonic() - armed_at

    assert rows == []
    assert waited >= SHORT_DELAY_SECONDS * 0.9


def test_leaving_the_context_without_arm_releases_the_lock_promptly(tmp_path: Path) -> None:
    """Exiting the context ends the hold at once, well inside the configured delay."""
    started_at = time.monotonic()
    with hold_cache_lock(LONG_DELAY_SECONDS, tmp_path) as lock:
        database_path = lock.database_path
    exit_seconds = time.monotonic() - started_at

    assert exit_seconds < LONG_DELAY_SECONDS / 10
    assert _select_locations(database_path, timeout=0) == []


def test_entering_a_lock_whose_database_cannot_be_opened_raises(tmp_path: Path) -> None:
    """A database path under a missing directory makes entry raise, and leaves no holder thread running.

    hold_cache_lock creates the file before it returns, so a missing directory fails there; this test
    builds the CacheLock directly to reach the holder's own open. Entry runs on a helper thread with a
    bounded join, so a holder that never reports back fails the test instead of hanging it.
    """
    lock = CacheLock(tmp_path / "missing" / "cache.sqlite3", SHORT_DELAY_SECONDS)
    raised: list[BaseException] = []

    def enter() -> None:
        try:
            with lock:
                pass
        except BaseException as error:  # noqa: BLE001 - the test inspects whatever entry raised.
            raised.append(error)

    entering = threading.Thread(target=enter, name="cache-lock-entry", daemon=True)
    entering.start()
    entering.join(RELEASE_WAIT_SECONDS)

    assert not entering.is_alive(), "entering the lock did not return or raise"
    assert len(raised) == 1
    assert isinstance(raised[0], sqlite3.OperationalError)
    assert not any(thread.name == "cache-lock-holder" for thread in threading.enumerate())
