"""ABOUTME: GeoEnrichmentWorkflow, which runs get_ip then get_location to enrich a caller's address.
ABOUTME: Both activities share one generous start_to_close and one schedule_to_close budget.

The budgets stay wide (120 seconds and 150 seconds) because the lesson is read from the worker,
not from a timeout. get_location also carries a fixed heartbeat_timeout of 5 seconds, shorter than
its 8-second poll interval; it is scenery for the exercise, not a value to tune. There is no custom
retry policy: the geo activities use the Temporal default, like every other activity here.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from activities import get_ip, get_location
    from shared import GeoEnrichmentInput, GeoEnrichmentOutput

GEO_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=120)
"""Budget for a single activity attempt, generous enough that a long wait is not cut off."""

GEO_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=150)
"""Overall budget from schedule to close."""

GEO_HEARTBEAT_TIMEOUT: timedelta = timedelta(seconds=5)
"""Fixed heartbeat_timeout on get_location. Scenery for the exercise, not a value to tune."""


@workflow.defn
class GeoEnrichmentWorkflow:
    """Fetch the caller's IP and look up its location."""

    @workflow.run
    async def run(self, args: GeoEnrichmentInput) -> GeoEnrichmentOutput:
        """Run get_ip then get_location and return the enriched address.

        Args:
            args: Whether get_location polls the simulated slow job instead of the public providers.

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
            args=[ip, args.slow_job],
            heartbeat_timeout=GEO_HEARTBEAT_TIMEOUT,
            start_to_close_timeout=GEO_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
        )
        return GeoEnrichmentOutput(ip=ip, location=location)
