"""ABOUTME: GeoEnrichmentWorkflow, which runs get_ip then get_location to enrich a caller's address.
ABOUTME: Both activities share one generous start_to_close and one schedule_to_close budget.

The budgets stay wide (120 seconds and 150 seconds) because the lesson is read from the worker,
not from a timeout. There is no heartbeat_timeout and no custom retry policy: the geo activities
use the Temporal default, like every other activity here.
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


@workflow.defn
class GeoEnrichmentWorkflow:
    """Fetch the caller's IP and look up its location."""

    @workflow.run
    async def run(self, args: GeoEnrichmentInput) -> GeoEnrichmentOutput:
        """Run get_ip then get_location and return the enriched address.

        Args:
            args: The optional location cache path that get_location reads before the providers.

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
            args=[ip, args.location_cache_path],
            start_to_close_timeout=GEO_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
        )
        return GeoEnrichmentOutput(ip=ip, location=location)
