"""ABOUTME: Contract tests for the shared workflow payloads and the task queue constant.
ABOUTME: Pins the healthy defaults, the frozen payloads, and the exact task queue name.
"""

import dataclasses

import pytest

from temporal_async_debug.shared import (
    TASK_QUEUE,
    GeoEnrichmentInput,
    GeoEnrichmentOutput,
    OrderReceiptInput,
    OrderReceiptOutput,
)


def test_geo_input_block_seconds_defaults_to_zero() -> None:
    """A GeoEnrichmentInput built with no arguments applies no mode delay."""
    assert GeoEnrichmentInput().block_seconds == 0.0


def test_geo_input_mode_defaults_to_block() -> None:
    """Mode defaults to "block", so only a switch to "slow" needs an explicit flag."""
    assert GeoEnrichmentInput().mode == "block"


@pytest.mark.parametrize(
    ("payload", "attribute"),
    [
        (GeoEnrichmentInput(), "mode"),
        (GeoEnrichmentOutput(ip="203.0.113.7", location="Austin, Texas, United States"), "ip"),
        (OrderReceiptInput(order_id="order-1", item_count=3, unit_price_cents=1999), "order_id"),
        (OrderReceiptOutput(receipt="order order-1: 59.97 USD"), "receipt"),
    ],
)
def test_workflow_payloads_are_frozen(payload: object, attribute: str) -> None:
    """Every payload crossing the workflow boundary rejects mutation after construction."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(payload, attribute, "mutated")


def test_geo_input_round_trips_explicit_values() -> None:
    """Explicit values survive construction, and the positional field order is seconds, mode."""
    geo_input = GeoEnrichmentInput(block_seconds=30.0, mode="slow")

    assert geo_input.block_seconds == 30.0
    assert geo_input.mode == "slow"
    assert geo_input == GeoEnrichmentInput(30.0, "slow")


def test_task_queue_name_is_stable() -> None:
    """The worker and the starter agree on this exact task queue name."""
    assert TASK_QUEUE == "async-debug-task-queue"
