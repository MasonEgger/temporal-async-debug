"""ABOUTME: Frozen payload dataclasses and the task queue name shared across the exercise copy.
ABOUTME: The three workflow types, their activities, the worker, and the starter import from here.

Every payload here crosses the Temporal workflow boundary, so each one stays small, frozen, and
JSON-serializable. Three unrelated workflow types share this module and the worker behind it: a
geo-enrichment lookup, an order-receipt build, and a sales rollup. In this exercise's fleet, two
Workers run the same code and poll the same task queue.

The geo input carries the path of a SQLite location cache, never a connection, because only plain
values cross the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

TASK_QUEUE: str = "async-debug-task-queue"
"""Task queue that the worker polls and the starter submits to."""


@dataclass(frozen=True)
class GeoEnrichmentInput:
    """Input to GeoEnrichmentWorkflow, which looks up the caller's IP and location.

    Attributes:
        location_cache_path: Path of a SQLite location cache that get_location reads before it
            asks the geo providers. Defaults to None, meaning the run skips the cache and asks the
            providers directly.
    """

    location_cache_path: str | None = None


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
