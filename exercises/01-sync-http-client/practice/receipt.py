"""ABOUTME: OrderReceiptWorkflow and its three fast activities, ordinary correct code with no network.
ABOUTME: It shares a worker with GeoEnrichmentWorkflow and is what breaks when that workflow misbehaves.

Nothing here is broken. The activities validate an order, compute its total, and format a receipt,
all in memory and in microseconds. This workflow exists so the tutorial can show that a problem in a
completely unrelated workflow takes it down too, purely because they share one worker and one event
loop. When the reader sees this instant, no-network workflow stall behind a frozen loop and
complete late, the shared-fate lesson lands.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from shared import OrderReceiptInput, OrderReceiptOutput

ACTIVITY_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=5)
"""Budget for a single receipt activity attempt; generous, since each is instant."""

ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=10)
"""Overall budget from schedule to close; a jammed worker makes even this trivial work breach it."""


@activity.defn
async def validate_order(order_id: str, item_count: int) -> str:
    """Confirm the order has at least one item and return its id.

    Args:
        order_id: Identifier for the order.
        item_count: Number of items ordered.

    Returns:
        The order id, unchanged, once the order is valid.

    Raises:
        ValueError: If item_count is not positive.
    """
    if item_count <= 0:
        raise ValueError(f"order {order_id} has no items")
    return order_id


@activity.defn
async def compute_total(item_count: int, unit_price_cents: int) -> int:
    """Return the order total in cents.

    Args:
        item_count: Number of items ordered.
        unit_price_cents: Price per item, in cents.

    Returns:
        The total price in cents.
    """
    return item_count * unit_price_cents


@activity.defn
async def format_receipt(order_id: str, total_cents: int) -> str:
    """Format a human-readable receipt line for the order.

    Args:
        order_id: Identifier for the order.
        total_cents: Order total in cents.

    Returns:
        A receipt line such as ``order abc: 59.97 USD``.
    """
    return f"order {order_id}: {total_cents / 100:.2f} USD"


@workflow.defn
class OrderReceiptWorkflow:
    """Validate an order, compute its total, and format a receipt.

    OrderReceiptWorkflow is ordinary, correct, fast code that touches no network. It shares a worker
    with GeoEnrichmentWorkflow on purpose, so that any failure it suffers is clearly caused by the
    worker's event loop being frozen, not by anything wrong here.
    """

    @workflow.run
    async def run(self, args: OrderReceiptInput) -> OrderReceiptOutput:
        """Run the three receipt activities in sequence and return the receipt.

        Args:
            args: The order id, item count, and unit price to build the receipt from.

        Returns:
            An OrderReceiptOutput carrying the formatted receipt line.
        """
        order_id = await workflow.execute_activity(
            validate_order,
            args=[args.order_id, args.item_count],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
        )
        total_cents = await workflow.execute_activity(
            compute_total,
            args=[args.item_count, args.unit_price_cents],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
        )
        receipt = await workflow.execute_activity(
            format_receipt,
            args=[order_id, total_cents],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
        )
        return OrderReceiptOutput(receipt=receipt)
