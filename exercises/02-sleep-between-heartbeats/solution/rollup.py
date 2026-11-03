"""ABOUTME: SalesRollupWorkflow and its one activity, ordinary correct code with a short cooperative pause.
ABOUTME: It shares a worker with GeoEnrichmentWorkflow and is what a freeze catches in-flight.

Nothing here is broken. The activity sums an in-memory list of sales figures after a brief
cooperative pause, standing in for a few seconds of real aggregation work. Unlike the instant
OrderReceiptWorkflow, this bystander is still running when a freeze lands, so the freeze fails it
with an activity timeout instead of only stalling it. The in-flight attempt times out at its
start_to_close, the default retry policy schedules another attempt the frozen worker cannot pick
up, and the activity finally fails with a ScheduleToClose timeout whose cause is that StartToClose
timeout. This workflow exists so the tutorial can show that in-flight, cross-type activity-timeout
damage, not just a stalled queue.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from shared import SalesRollupInput, SalesRollupOutput

ACTIVITY_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=10)
"""Budget for a single roll_up_sales attempt; generous relative to the few seconds of work."""

ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=20)
"""Overall budget from schedule to close; a frozen loop makes even this short work breach it."""

FIGURES: tuple[int, ...] = (1_200, 950, 3_100, 780)
"""Placeholder per-region sales figures, in whole currency units, standing in for a real data source."""


@activity.defn
async def roll_up_sales(period: str, work_seconds: float = 5.0) -> str:
    """Sum the in-memory sales figures for a period after a short cooperative pause.

    Args:
        period: Label for the period being rolled up, for example "2026-09".
        work_seconds: Seconds to await before returning, standing in for real aggregation work.
            Defaults to 5.0, long enough that the starter's freeze reliably lands while this is
            still in flight, and still well under the 10-second start_to_close. Tests pass 0.0 to
            skip the pause.

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
    cooperative pause is long enough that a freeze landing mid-run catches it in-flight, failing
    it with a ScheduleToClose timeout (StartToClose as the cause) instead of only stalling it.
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
