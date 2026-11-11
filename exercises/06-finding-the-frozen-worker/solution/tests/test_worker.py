"""ABOUTME: Tests for build_worker: the executor size and what the Worker registers.
ABOUTME: Each builds the real Worker against a time-skipping test server and reads its config.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from receipt import OrderReceiptWorkflow
from rollup import SalesRollupWorkflow
from shared import TASK_QUEUE
from temporalio.testing import WorkflowEnvironment
from worker import MAX_CONCURRENT_ACTIVITIES, build_worker
from workflow import GeoEnrichmentWorkflow

EXPECTED_ACTIVITY_NAMES: frozenset[str] = frozenset(
    {"get_ip", "get_location", "validate_order", "compute_total", "format_receipt", "roll_up_sales"}
)
"""Every activity the three workflow types schedule, all of which share the one worker."""


async def test_worker_executor_has_a_thread_for_every_activity_slot() -> None:
    """The activity_executor is a thread pool with exactly max_concurrent_activities threads."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        config = build_worker(environment.client).config()

    executor = config["activity_executor"]
    assert isinstance(executor, ThreadPoolExecutor)
    try:
        assert config["max_concurrent_activities"] == MAX_CONCURRENT_ACTIVITIES
        # _max_workers is private; ThreadPoolExecutor offers no public way to read its size.
        assert executor._max_workers == MAX_CONCURRENT_ACTIVITIES  # noqa: SLF001
    finally:
        executor.shutdown(wait=False)


async def test_build_worker_registers_every_workflow_type_and_activity() -> None:
    """The one worker carries all three workflow types and every activity they schedule, on the shared task queue."""
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        config = build_worker(environment.client).config()

    executor = config["activity_executor"]
    assert isinstance(executor, ThreadPoolExecutor)
    executor.shutdown(wait=False)
    assert config["task_queue"] == TASK_QUEUE
    assert {activity_fn.__name__ for activity_fn in config["activities"]} == EXPECTED_ACTIVITY_NAMES
    assert set(config["workflows"]) == {GeoEnrichmentWorkflow, OrderReceiptWorkflow, SalesRollupWorkflow}
