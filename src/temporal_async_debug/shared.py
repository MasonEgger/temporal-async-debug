"""ABOUTME: Frozen payload dataclasses and the task queue name shared across the demo.
ABOUTME: Both workflow types, their activities, the worker, and the starter import from here.

Every payload here crosses the Temporal workflow boundary, so each one stays small,
frozen, and JSON-serializable. Two unrelated workflow types share this module and the
worker behind it: a geo-enrichment lookup and an order-receipt build. ``GeoEnrichmentInput``
carries the two knobs that drive the demo's failure modes: how long an activity delays, and
which kind of delay it uses.
"""

from __future__ import annotations

from dataclasses import dataclass

TASK_QUEUE: str = "async-debug-task-queue"
"""Task queue that the worker polls and the starter submits to."""


@dataclass(frozen=True)
class GeoEnrichmentInput:
    """Input to GeoEnrichmentWorkflow, which looks up the caller's IP and location.

    Attributes:
        block_seconds: Seconds of delay each activity applies before its HTTP call.
            Defaults to 0.0, the healthy value, meaning no delay at all.
        mode: Which delay to apply when block_seconds is above zero. "block" calls
            time.sleep, which freezes the worker's event loop and is the deliberate
            bug this demo teaches. "slow" awaits asyncio.sleep, which is cooperative
            but still holds an activity slot for the duration.
    """

    block_seconds: float = 0.0
    mode: str = "block"


@dataclass(frozen=True)
class GeoEnrichmentOutput:
    """Result of GeoEnrichmentWorkflow, assembled from both activity results.

    Attributes:
        ip: Public IP address returned by the get_ip activity.
        location: Human-readable location returned by the get_location activity.
    """

    ip: str
    location: str


@dataclass(frozen=True)
class OrderReceiptInput:
    """Input to OrderReceiptWorkflow, an ordinary fast workflow with no network calls.

    Attributes:
        order_id: Identifier for the order this receipt is built for.
        item_count: Number of items ordered.
        unit_price_cents: Price per item, in cents.
    """

    order_id: str
    item_count: int
    unit_price_cents: int


@dataclass(frozen=True)
class OrderReceiptOutput:
    """Result of OrderReceiptWorkflow.

    Attributes:
        receipt: Human-readable receipt line for the order.
    """

    receipt: str
