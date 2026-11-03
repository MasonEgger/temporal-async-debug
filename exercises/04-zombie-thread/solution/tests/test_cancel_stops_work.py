"""ABOUTME: Proof that a cancel reaches get_location's work and stops it, and that the executor fits the slots.
ABOUTME: The cancel test runs the def activity under ActivityEnvironment; the second builds the real worker.

ActivityEnvironment runs a ``def`` activity on the calling thread and, on ``cancel()``, raises
``temporalio.exceptions.CancelledError`` in that thread, the way a Worker does through a
heartbeat. A ``def`` activity that heartbeats between steps therefore stops mid-work, while an
``async def`` activity that hands its work to ``asyncio.to_thread`` has no thread of its own to
interrupt. Both tests fail against that shape.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from activities import get_location
from conftest import MOCKED_IP
from temporalio.exceptions import CancelledError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from worker import MAX_CONCURRENT_ACTIVITIES, build_worker

if TYPE_CHECKING:
    import respx

TOTAL_STEPS: int = 20
"""The work's length; a cancel that works leaves most of it undone."""

CANCEL_AT_HEARTBEAT: int = 3
"""The heartbeat on which the test requests the cancel."""


def test_cancel_stops_the_work_at_the_next_heartbeat(
    mocked_network: respx.MockRouter, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A cancel requested mid-work raises CancelledError in the work, which stops without finishing."""
    monkeypatch.setattr("activities.STEP_SECONDS", 0.01)
    environment = ActivityEnvironment()
    heartbeat_steps: list[int] = []

    def on_heartbeat(step: int) -> None:
        heartbeat_steps.append(step)
        if step == CANCEL_AT_HEARTBEAT:
            environment.cancel()

    environment.on_heartbeat = on_heartbeat

    with pytest.raises(CancelledError):
        environment.run(get_location, MOCKED_IP, TOTAL_STEPS)

    assert heartbeat_steps[0] == 1
    assert CANCEL_AT_HEARTBEAT <= len(heartbeat_steps) <= CANCEL_AT_HEARTBEAT + 1
    progress = [line for line in capsys.readouterr().out.splitlines() if "step" in line and "cancelled" not in line]
    assert len(progress) < TOTAL_STEPS
    assert mocked_network.calls.call_count == 1


async def test_worker_executor_has_a_thread_for_every_activity_slot() -> None:
    """The activity_executor is a thread pool with at least max_concurrent_activities threads."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        config = build_worker(environment.client).config()

    executor = config["activity_executor"]
    assert isinstance(executor, ThreadPoolExecutor)
    try:
        assert config["max_concurrent_activities"] == MAX_CONCURRENT_ACTIVITIES
        # _max_workers is private; ThreadPoolExecutor offers no public way to read its size.
        assert executor._max_workers >= MAX_CONCURRENT_ACTIVITIES  # noqa: SLF001
    finally:
        executor.shutdown(wait=False)
