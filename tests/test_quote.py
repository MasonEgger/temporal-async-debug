"""ABOUTME: Tests for the price-quote activity and workflow, the schedule-to-start sample.
ABOUTME: Confirms the quote math, its schedule_to_start configuration, and the happy/concurrent paths.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import httpx
import pytest
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from temporal_async_debug.quote import PriceQuoteWorkflow, compute_quote, quote_activity_options
from temporal_async_debug.shared import TASK_QUEUE, PriceQuoteInput, PriceQuoteOutput
from tests.history import scheduled_activity_attributes


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if the quote activity issues an httpx request; this code must touch no network.

    Every httpx verb routes through AsyncClient.request, so replacing it with a raiser turns any
    accidental network call in the quote path into a test failure rather than a silent dependency.
    The Temporal test server uses its own gRPC bridge, not httpx, so this does not disturb it.
    """

    async def _forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("price-quote activities must not touch the network")

    monkeypatch.setattr(httpx.AsyncClient, "request", _forbidden)


async def test_compute_quote_returns_the_sku_and_total() -> None:
    """compute_quote prices a known sku from the in-memory table."""
    result = await ActivityEnvironment().run(compute_quote, "WIDGET-1", 3)
    assert "WIDGET-1" in result
    assert "59.97" in result


def test_quote_activity_options_sets_a_short_schedule_to_start_timeout() -> None:
    """quote_activity_options is the one place schedule_to_start_timeout is configured."""
    options = quote_activity_options()
    assert options.schedule_to_start_timeout == timedelta(seconds=5)
    assert options.start_to_close_timeout == timedelta(seconds=5)


async def test_price_quote_workflow_happy_path_returns_the_quote() -> None:
    """The workflow quotes the given sku with no network involved."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[PriceQuoteWorkflow],
            activities=[compute_quote],
        ),
    ):
        result = await env.client.execute_workflow(
            PriceQuoteWorkflow.run,
            PriceQuoteInput(sku="WIDGET-1", quantity=3),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, PriceQuoteOutput)
    assert "WIDGET-1" in result.quote
    assert result.quote != ""


async def test_price_quote_workflow_passes_schedule_to_start_through_to_the_scheduled_activity() -> None:
    """The scheduled compute_quote carries the 5-second schedule_to_start, read back from history."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[PriceQuoteWorkflow],
            activities=[compute_quote],
        ),
    ):
        handle = await env.client.start_workflow(
            PriceQuoteWorkflow.run,
            PriceQuoteInput(sku="WIDGET-1"),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )
        await handle.result()
        scheduled = await scheduled_activity_attributes(handle)

    assert len(scheduled) == 1
    assert scheduled[0].activity_type.name == "compute_quote"
    assert scheduled[0].schedule_to_start_timeout.ToTimedelta() == timedelta(seconds=5)
    assert scheduled[0].start_to_close_timeout.ToTimedelta() == timedelta(seconds=5)


async def test_price_quote_workflow_runs_concurrently_with_distinct_skus() -> None:
    """Several concurrent PriceQuoteWorkflow runs each reflect their own sku and quantity."""
    skus_and_quantities = [("WIDGET-1", 1), ("WIDGET-2", 2), ("GADGET-1", 3)]
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[PriceQuoteWorkflow],
            activities=[compute_quote],
        ),
    ):
        with env.auto_time_skipping_disabled():
            results = await asyncio.gather(
                *(
                    env.client.execute_workflow(
                        PriceQuoteWorkflow.run,
                        PriceQuoteInput(sku=sku, quantity=quantity),
                        id=str(uuid.uuid4()),
                        task_queue=TASK_QUEUE,
                    )
                    for sku, quantity in skus_and_quantities
                )
            )

    for (sku, quantity), result in zip(skus_and_quantities, results, strict=True):
        assert isinstance(result, PriceQuoteOutput)
        assert sku in result.quote
        assert str(quantity) in result.quote
