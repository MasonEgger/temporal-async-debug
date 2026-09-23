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

VALID_MODES: tuple[str, ...] = ("block", "cpu", "slow", "slow_heartbeat", "stuck_no_heartbeat")
"""Every delay mode an activity can apply, each demonstrating a distinct failure signature.

- "block": time.sleep freezes the worker's single event loop (uncancellable).
- "cpu": a busy loop pins the GIL and freezes the loop too, but burns 100% CPU doing it.
- "slow": asyncio.sleep waits cooperatively, holding an activity slot but not the loop.
- "slow_heartbeat": asyncio.sleep in steps with heartbeats between them, the correct way
    to hold a slot for legitimate long-running work.
- "stuck_no_heartbeat": asyncio.sleep with no heartbeat, tripping a heartbeat timeout.
"""


@dataclass(frozen=True)
class GeoEnrichmentInput:
    """Input to GeoEnrichmentWorkflow, which looks up the caller's IP and location.

    Attributes:
        block_seconds: Seconds of delay each activity applies before its HTTP call.
            Defaults to 0.0, the healthy value, meaning no delay at all.
        mode: Which delay to apply when block_seconds is above zero. One of
            shared.VALID_MODES. Freezing modes ("block", "cpu") stop the worker's
            entire event loop and are the deliberate bugs this demo teaches.
            Cooperative modes ("slow", "slow_heartbeat", "stuck_no_heartbeat")
            await asyncio.sleep instead, holding an activity slot without freezing
            the loop; see activities._apply_mode for what each mode does.
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


@dataclass(frozen=True)
class SalesRollupInput:
    """Input to SalesRollupWorkflow, an ordinary short-work workflow with no network calls.

    Attributes:
        period: Label for the period being rolled up, for example "2026-09".
    """

    period: str


@dataclass(frozen=True)
class SalesRollupOutput:
    """Result of SalesRollupWorkflow.

    Attributes:
        summary: Human-readable summary of the period's rolled-up sales total.
    """

    summary: str


@dataclass(frozen=True)
class PriceQuoteInput:
    """Input to PriceQuoteWorkflow, the schedule-to-start sample with no network calls.

    Attributes:
        sku: Identifier for the item to quote a price for.
        quantity: Number of units to quote. Defaults to 1.
    """

    sku: str
    quantity: int = 1


@dataclass(frozen=True)
class PriceQuoteOutput:
    """Result of PriceQuoteWorkflow.

    Attributes:
        quote: Human-readable price quote for the sku and quantity.
    """

    quote: str
