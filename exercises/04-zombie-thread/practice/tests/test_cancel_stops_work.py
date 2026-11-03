"""ABOUTME: Stub for the Part D cancel test; you write the body.
ABOUTME: The finished version lives in ../solution/tests/test_cancel_stops_work.py.
"""

from __future__ import annotations

import pytest


def test_cancel_stops_the_work_at_the_next_heartbeat() -> None:
    """A cancel requested mid-work reaches get_location's work and stops it."""
    # TODO PART D: Run get_location under temporalio.testing.ActivityEnvironment with a patched-down
    # STEP_SECONDS, request a cancel from the environment's on_heartbeat callback, and assert that
    # CancelledError is raised and the work stopped long before its last step. The test must fail
    # while the work runs under asyncio.to_thread with no heartbeat.
    pytest.fail("TODO PART D: write the cancel test")


async def test_worker_executor_has_a_thread_for_every_activity_slot() -> None:
    """The worker's activity_executor has at least max_concurrent_activities threads."""
    # TODO PART D: Build the worker with build_worker, read its config()["activity_executor"], and
    # assert it is a ThreadPoolExecutor whose pool size is at least max_concurrent_activities.
    pytest.fail("TODO PART D: write the executor-size test")
