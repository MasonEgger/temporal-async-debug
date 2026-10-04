"""ABOUTME: Tests for the order-receipt activities and workflow, the ordinary no-network code.
ABOUTME: Confirms the receipt math and formatting, and the happy path under a time-skipping env.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
import pytest
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from temporal_async_debug.receipt import (
    ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
    ACTIVITY_START_TO_CLOSE_TIMEOUT,
    OrderReceiptWorkflow,
    compute_total,
    format_receipt,
    validate_order,
)
from temporal_async_debug.shared import TASK_QUEUE, OrderReceiptInput, OrderReceiptOutput


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any receipt activity issues an httpx request; this code must touch no network.

    Every httpx verb routes through AsyncClient.request, so replacing it with a raiser turns any
    accidental network call in the receipt path into a test failure rather than a silent dependency.
    The Temporal test server uses its own gRPC bridge, not httpx, so this does not disturb it.
    """

    async def _forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("order-receipt activities must not touch the network")

    monkeypatch.setattr(httpx.AsyncClient, "request", _forbidden)


def test_receipt_timeouts_are_pinned() -> None:
    """Receipt activities get a 5-second start_to_close inside a 10-second schedule_to_close."""
    assert timedelta(seconds=5) == ACTIVITY_START_TO_CLOSE_TIMEOUT
    assert timedelta(seconds=10) == ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT


async def test_compute_total_multiplies_count_by_unit_price() -> None:
    """compute_total returns item_count times unit_price_cents."""
    assert await ActivityEnvironment().run(compute_total, 3, 1999) == 5997


async def test_format_receipt_renders_dollars_with_two_decimals() -> None:
    """format_receipt turns a cents total into a dollars-and-cents receipt line."""
    assert await ActivityEnvironment().run(format_receipt, "order-1", 5997) == "order order-1: 59.97 USD"


async def test_validate_order_returns_the_id_for_a_valid_order() -> None:
    """validate_order passes a positive-item order straight through by returning its id."""
    assert await ActivityEnvironment().run(validate_order, "order-1", 3) == "order-1"


async def test_order_receipt_workflow_happy_path_returns_the_receipt() -> None:
    """The workflow validates, totals, and formats the order with no network involved."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[OrderReceiptWorkflow],
            activities=[validate_order, compute_total, format_receipt],
        ),
    ):
        result = await env.client.execute_workflow(
            OrderReceiptWorkflow.run,
            OrderReceiptInput(order_id="order-1", item_count=3, unit_price_cents=1999),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, OrderReceiptOutput)
    assert result.receipt == "order order-1: 59.97 USD"
