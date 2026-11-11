"""ABOUTME: Holds an exclusive lock on a temporary SQLite location cache, so a lookup against it waits.
ABOUTME: The exercise 06 starter holds it for the bad run; the tests hold it from inside the test.

The lock stands in for a slow or contended synchronous database call, the kind a real Activity
makes through a database driver that has no async API. A holder thread opens a temporary
database file in rollback-journal mode, creates the empty ``locations`` table, and holds a
``BEGIN EXCLUSIVE`` transaction, so every other connection's ``SELECT`` waits until the
transaction ends or the reader's own ``timeout`` runs out.

The hold is counted from ``arm()``, not from the moment the lock is taken. The starter takes the
lock before it submits anything and calls ``arm()`` right after it submits the bad run, so the
freeze is about as long as the configured delay. Leaving the context ends the hold at once,
armed or not.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from types import TracebackType

LOCATIONS_SCHEMA: str = "CREATE TABLE IF NOT EXISTS locations (ip TEXT PRIMARY KEY, location TEXT)"
"""The cache table: one cached location line per IP address."""


class CacheLock:
    """A temporary location cache and the thread that holds its exclusive lock.

    Entering the context starts the holder thread and returns once the lock is held. Exiting it
    ends the hold at once, armed or not, and waits for the holder to commit.

    Attributes:
        database_path: The cache's database file, for the bad run's ``location_cache_path``.
    """

    def __init__(self, database_path: Path, delay_seconds: float) -> None:
        """Prepare the holder thread without starting it.

        Args:
            database_path: The database file the holder opens and locks.
            delay_seconds: How long the hold lasts once ``arm()`` is called.
        """
        self.database_path = database_path
        self._delay_seconds = delay_seconds
        self._armed = threading.Event()
        self._closing = threading.Event()
        self._held = threading.Event()
        self._error: sqlite3.Error | None = None
        self._thread = threading.Thread(target=self._hold, name="cache-lock-holder", daemon=True)

    def arm(self) -> None:
        """Start counting the hold: the lock lets go ``delay_seconds`` from now."""
        self._armed.set()

    def __enter__(self) -> Self:
        """Start the holder thread and return once it holds the lock.

        Returns:
            This CacheLock.

        Raises:
            sqlite3.Error: If the holder could not open the database, create the table, or take
                the lock. The holder thread has ended by the time it is raised.
        """
        self._thread.start()
        self._held.wait()
        if self._error is not None:
            self._thread.join()
            raise self._error
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """End the hold at once, armed or not, and wait for the holder thread to commit."""
        self._closing.set()
        self._armed.set()
        self._thread.join()

    def _hold(self) -> None:
        """Take the exclusive lock, wait for ``arm()``, wait out the delay, then commit.

        Any ``sqlite3.Error`` while taking the lock is kept for ``__enter__`` to raise, and the
        thread ends there. ``_held`` is set either way, so ``__enter__`` never waits on a dead thread.
        """
        try:
            connection = self._take_lock()
        except sqlite3.Error as error:
            self._error = error
            return
        finally:
            self._held.set()

        with closing(connection):
            # __exit__ sets both events, so leaving the context cuts either wait short.
            self._armed.wait()
            self._closing.wait(self._delay_seconds)
            connection.execute("COMMIT")

    def _take_lock(self) -> sqlite3.Connection:
        """Open the database, create the locations table, and begin the exclusive transaction.

        Returns:
            The open connection, inside its ``BEGIN EXCLUSIVE`` transaction.

        Raises:
            sqlite3.Error: If the database cannot be opened, the table created, or the lock taken.
                A connection that opened is closed before the error propagates.
        """
        # isolation_level=None leaves transactions to the explicit BEGIN and COMMIT.
        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            # A rollback journal, unlike WAL, keeps readers out while a writer holds EXCLUSIVE.
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute(LOCATIONS_SCHEMA)
            connection.execute("BEGIN EXCLUSIVE")
        except sqlite3.Error:
            connection.close()
            raise
        return connection


def hold_cache_lock(delay_seconds: float, directory: Path) -> CacheLock:
    """Create a temporary location cache under directory, ready to hold its exclusive lock.

    Use the result as a context manager: ``with hold_cache_lock(30.0, directory) as lock``. The
    lock is held from the moment the context is entered until ``delay_seconds`` after ``arm()``,
    or until the context exits, whichever comes first. The database file stays in directory
    afterwards; the caller owns the directory and its cleanup.

    Args:
        delay_seconds: How long the hold lasts once ``arm()`` is called.
        directory: Where the database file is created.

    Returns:
        The CacheLock, with the database path and ``arm()``.

    Raises:
        OSError: If the database file cannot be created in directory, for example when it is missing.
    """
    file_descriptor, raw_path = tempfile.mkstemp(prefix="location-cache-", suffix=".sqlite3", dir=directory)
    # SQLite reads an empty file as an empty database, so only the unique name is needed.
    os.close(file_descriptor)
    return CacheLock(Path(raw_path), delay_seconds)
