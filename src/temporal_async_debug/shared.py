"""ABOUTME: Frozen payload dataclasses and the task queue name shared across the demo.
ABOUTME: The three workflow types, their activities, the worker, and the starter import from here.

Every payload here crosses the Temporal workflow boundary, so each one stays small,
frozen, and JSON-serializable. Three unrelated workflow types share this module and the
worker behind it: a geo-enrichment lookup, an order-receipt build, and a sales rollup.
``GeoEnrichmentInput`` carries the two knobs that drive the demo's failure modes: how long an
activity freezes the loop, and which kind of freeze it uses.
"""

from __future__ import annotations

from dataclasses import dataclass

TASK_QUEUE: str = "async-debug-task-queue"
"""Task queue that the worker polls and the starter submits to."""

VALID_MODES: tuple[str, ...] = ("block", "cpu")
"""Every delay mode an activity can apply, each freezing the worker's one event loop.

- "block": time.sleep freezes the loop (uncancellable) at near-zero CPU.
- "cpu": a busy loop pins the GIL and freezes the loop too, but burns 100% CPU doing it.
"""


@dataclass(frozen=True)
class GeoEnrichmentInput:
    """Input to GeoEnrichmentWorkflow, which looks up the caller's IP and location.

    Attributes:
        block_seconds: Seconds of delay each activity applies before its HTTP call.
            Defaults to 0.0, the healthy value, meaning no delay at all.
        mode: Which delay to apply when block_seconds is above zero. One of
            shared.VALID_MODES. Both modes stop the worker's entire event loop and are the
            deliberate bugs this demo teaches; see activities._apply_mode.
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
