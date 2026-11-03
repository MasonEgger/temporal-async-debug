"""ABOUTME: GeoEnrichmentWorkflow, which runs get_ip then get_location to enrich a caller's address.
ABOUTME: get_location runs under a 5-second heartbeat_timeout; both activities share one overall budget.

get_location carries a heartbeat_timeout, so the server fails an attempt that goes five seconds
without a heartbeat. The overall budget is 20 seconds, short enough that a run whose attempts keep
failing ends in about that long. There is no custom retry policy: the geo activities use the
Temporal default, like every other activity here.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from activities import get_ip, get_location
    from shared import GeoEnrichmentInput, GeoEnrichmentOutput

GEO_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=20)
"""Budget for a single activity attempt, the same as the overall budget below."""

GEO_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=20)
"""Overall budget from schedule to close, wide enough for a ten-second job and a few failed attempts."""

GEO_HEARTBEAT_TIMEOUT: timedelta = timedelta(seconds=5)
"""How long get_location may go without a heartbeat before the server fails the attempt."""


@workflow.defn
class GeoEnrichmentWorkflow:
    """Fetch the caller's IP and look up its location."""

    @workflow.run
    async def run(self, args: GeoEnrichmentInput) -> GeoEnrichmentOutput:
        """Run get_ip then get_location and return the enriched address.

        Args:
            args: The step count get_location uses for its blocking work.

        Returns:
            A GeoEnrichmentOutput carrying the IP and the location.
        """
        ip = await workflow.execute_activity(
            get_ip,
            start_to_close_timeout=GEO_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
        )
        location = await workflow.execute_activity(
            get_location,
            args=[ip, args.work_steps],
            start_to_close_timeout=GEO_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
            heartbeat_timeout=GEO_HEARTBEAT_TIMEOUT,
        )
        return GeoEnrichmentOutput(ip=ip, location=location)
