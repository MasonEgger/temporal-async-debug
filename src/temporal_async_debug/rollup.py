"""ABOUTME: SalesRollupWorkflow and its one activity, ordinary correct code with a short cooperative pause.
ABOUTME: It shares a worker with GeoEnrichmentWorkflow and is what a freeze catches in-flight.

Nothing here is broken. The activity sums an in-memory list of sales figures after a brief
cooperative pause, standing in for a couple of seconds of real aggregation work. Unlike the
instant OrderReceiptWorkflow, this bystander is still running when a freeze lands, so the freeze
trips its start_to_close timeout instead of only stalling it. This workflow exists so the tutorial
can show that in-flight, cross-type activity-timeout damage, not just a stalled queue.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from temporal_async_debug.shared import SalesRollupInput, SalesRollupOutput

ACTIVITY_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=10)
"""Budget for a single roll_up_sales attempt; generous relative to the couple of seconds of work."""

ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=20)
"""Overall budget from schedule to close; a saturated worker makes even this short work breach it."""

FIGURES: tuple[int, ...] = (1_200, 950, 3_100, 780)
"""Placeholder per-region sales figures, in whole currency units, standing in for a real data source."""


@activity.defn
async def roll_up_sales(period: str, work_seconds: float = 2.0) -> str:
    """Sum the in-memory sales figures for a period after a short cooperative pause.

    Args:
        period: Label for the period being rolled up, for example "2026-09".
        work_seconds: Seconds to await before returning, standing in for real aggregation work.
            Defaults to 2.0; tests pass 0.0 to skip the pause.

    Returns:
        A one-line summary naming the period and its total.
    """
    await asyncio.sleep(work_seconds)
    total = sum(FIGURES)
    return f"Sales rollup for {period}: total {total}"


@workflow.defn
class SalesRollupWorkflow:
    """Sum a period's sales figures, ordinary correct code that touches no network.

    SalesRollupWorkflow shares a worker with GeoEnrichmentWorkflow on purpose. Its short
    cooperative pause is long enough that a freeze landing mid-run catches it in-flight,
    tripping start_to_close instead of only stalling it.
    """

    @workflow.run
    async def run(self, args: SalesRollupInput) -> SalesRollupOutput:
        """Run roll_up_sales for the given period and return its summary.

        Args:
            args: The period to roll up sales for.

        Returns:
            A SalesRollupOutput carrying the summary line.
        """
        summary = await workflow.execute_activity(
            roll_up_sales,
            args=[args.period],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
        )
        return SalesRollupOutput(summary=summary)
