"""ABOUTME: Tests for the sales-rollup activity and workflow, the short-work no-network bystander.
ABOUTME: Confirms the rollup math and the happy and concurrent paths under a time-skipping env.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest
from temporalio import activity
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from temporal_async_debug.rollup import SalesRollupWorkflow, roll_up_sales
from temporal_async_debug.shared import TASK_QUEUE, SalesRollupInput, SalesRollupOutput


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if the rollup activity issues an httpx request; this code must touch no network.

    Every httpx verb routes through AsyncClient.request, so replacing it with a raiser turns any
    accidental network call in the rollup path into a test failure rather than a silent dependency.
    The Temporal test server uses its own gRPC bridge, not httpx, so this does not disturb it.
    """

    async def _forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("sales-rollup activities must not touch the network")

    monkeypatch.setattr(httpx.AsyncClient, "request", _forbidden)


async def test_roll_up_sales_returns_the_period_and_total_with_no_pause() -> None:
    """roll_up_sales sums the in-memory figures and names the period, with the pause skipped."""
    assert await ActivityEnvironment().run(roll_up_sales, "2026-09", 0.0) == "Sales rollup for 2026-09: total 6030"


async def test_sales_rollup_workflow_happy_path_returns_the_summary() -> None:
    """The workflow rolls up the period's sales with no network involved."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[SalesRollupWorkflow],
            activities=[roll_up_sales],
        ),
    ):
        result = await env.client.execute_workflow(
            SalesRollupWorkflow.run,
            SalesRollupInput(period="2026-09"),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, SalesRollupOutput)
    assert "2026-09" in result.summary
    assert result.summary != ""


async def test_sales_rollup_workflow_runs_concurrently_with_distinct_periods() -> None:
    """Several concurrent SalesRollupWorkflow runs each complete with their own period reflected.

    This stubs roll_up_sales with an instant stand-in rather than the real 2-second cooperative
    pause, since the activity's own timing is already covered by the ActivityEnvironment unit test
    above, and disables automatic time-skipping for the gather: three concurrent executions racing
    the time-skipping server's auto-advance against real activity dispatch is a proven source of
    flakiness (spurious start_to_close timeouts) that has nothing to do with the code under test.
    """

    @activity.defn(name="roll_up_sales")
    async def roll_up_sales_stub(period: str, work_seconds: float = 2.0) -> str:
        """Stand in for roll_up_sales, returning instantly so concurrency, not timing, is tested."""
        return f"Sales rollup for {period}: total 6030"

    periods = ["2026-01", "2026-02", "2026-03"]
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[SalesRollupWorkflow],
            activities=[roll_up_sales_stub],
        ),
    ):
        with env.auto_time_skipping_disabled():
            results = await asyncio.gather(
                *(
                    env.client.execute_workflow(
                        SalesRollupWorkflow.run,
                        SalesRollupInput(period=period),
                        id=str(uuid.uuid4()),
                        task_queue=TASK_QUEUE,
                    )
                    for period in periods
                )
            )

    for period, result in zip(periods, results, strict=True):
        assert isinstance(result, SalesRollupOutput)
        assert period in result.summary
