"""ABOUTME: PriceQuoteWorkflow and its one activity, the one sample that sets schedule_to_start_timeout.
ABOUTME: A stale quote is worthless, so this activity must start promptly or fail fast and visibly.

Nothing else in this demo sets schedule_to_start_timeout, because doing so is normally an
antipattern: it makes an activity fail the instant a worker falls behind, which is rarely what
production code wants. Here it is the deliberate teaching point. A price quote is worthless once
stale, so refusing to run a late quote is the legitimate routing use case, and the short timeout
doubles as a fast, visible signal that the worker is saturated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from temporal_async_debug.shared import PriceQuoteInput, PriceQuoteOutput

PRICE_TABLE_CENTS: dict[str, int] = {
    "WIDGET-1": 1_999,
    "WIDGET-2": 3_499,
    "GADGET-1": 7_999,
}
"""Placeholder unit prices, in cents, standing in for a real pricing service."""

DEFAULT_UNIT_PRICE_CENTS: int = 999
"""Unit price used for a sku not in PRICE_TABLE_CENTS, so any sku produces a quote."""


@dataclass(frozen=True)
class QuoteActivityOptions:
    """Activity execution options shared by PriceQuoteWorkflow and its tests.

    Attributes:
        start_to_close_timeout: Budget for a single compute_quote attempt.
        schedule_to_start_timeout: How long a quote may wait to start before it is too stale
            to be worth running.
    """

    start_to_close_timeout: timedelta
    schedule_to_start_timeout: timedelta


def quote_activity_options() -> QuoteActivityOptions:
    """Return the activity options PriceQuoteWorkflow uses to run compute_quote.

    Returns:
        The shared QuoteActivityOptions, so the workflow and its tests read one source.
    """
    return QuoteActivityOptions(
        start_to_close_timeout=timedelta(seconds=5),
        # ANTIPATTERN (deliberate, for teaching): a short schedule_to_start_timeout is normally
        # an antipattern; it is set here only because a stale quote is worthless, and to make
        # worker saturation fail fast and visibly. Correct: usually leave schedule_to_start unset
        # and size the worker to demand. Do not copy.
        schedule_to_start_timeout=timedelta(seconds=5),
    )


@activity.defn
async def compute_quote(sku: str, quantity: int) -> str:
    """Compute a price quote from the in-memory price table, near-instant and no network.

    Args:
        sku: Identifier for the item to quote a price for.
        quantity: Number of units to quote.

    Returns:
        A one-line quote naming the sku, quantity, and total price.
    """
    unit_price_cents = PRICE_TABLE_CENTS.get(sku, DEFAULT_UNIT_PRICE_CENTS)
    total_cents = unit_price_cents * quantity
    return f"Quote for {quantity} x {sku}: {total_cents / 100:.2f} USD"


@workflow.defn
class PriceQuoteWorkflow:
    """Compute a price quote, the sample that shows schedule_to_start_timeout firing.

    PriceQuoteWorkflow shares a worker with GeoEnrichmentWorkflow on purpose. Its activity is
    near-instant, so under a healthy worker it always starts immediately; its short
    schedule_to_start_timeout only fires when the worker is saturated and the quote would
    otherwise sit stale in the queue.
    """

    @workflow.run
    async def run(self, args: PriceQuoteInput) -> PriceQuoteOutput:
        """Run compute_quote for the given sku and quantity and return the quote.

        Args:
            args: The sku and quantity to quote a price for.

        Returns:
            A PriceQuoteOutput carrying the quote line.
        """
        options = quote_activity_options()
        quote = await workflow.execute_activity(
            compute_quote,
            args=[args.sku, args.quantity],
            start_to_close_timeout=options.start_to_close_timeout,
            schedule_to_start_timeout=options.schedule_to_start_timeout,
        )
        return PriceQuoteOutput(quote=quote)
