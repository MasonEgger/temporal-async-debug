"""ABOUTME: GeoEnrichmentWorkflow, which runs get_ip then get_location to enrich a caller's address.
ABOUTME: Realistic per-activity timeouts plus maximum_attempts=1 make a failure surface fast.

The two activities run in sequence: get_ip fetches the public address, then get_location looks it up.
Each runs with a 10-second start_to_close_timeout (a plausible bound for a quick HTTP call) and a
15-second schedule_to_close_timeout (an SLA that queued work breaches when the worker is jammed).
The retry policy caps attempts at one on purpose (see the antipattern marker) so the first failure
reaches the caller instead of being retried and hidden.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_async_debug.activities import get_ip, get_location
    from temporal_async_debug.shared import GeoEnrichmentInput, GeoEnrichmentOutput

ACTIVITY_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=10)
"""Budget for a single activity attempt once a worker has started it."""

ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=15)
"""Overall budget from schedule to close; queued work breaches this when the worker is jammed."""


@workflow.defn
class GeoEnrichmentWorkflow:
    """Fetch the caller's IP and look up its location.

    The workflow runs get_ip and then get_location, both of which can block the worker's event
    loop or hold an activity slot when their input asks them to. The maximum_attempts=1 retry
    policy lets the first failure surface to the caller instead of being retried silently.
    """

    @workflow.run
    async def run(self, args: GeoEnrichmentInput) -> GeoEnrichmentOutput:
        """Run get_ip then get_location and return the enriched address.

        Args:
            args: The block_seconds and mode that decide whether each activity blocks the
                worker's event loop or holds its slot.

        Returns:
            A GeoEnrichmentOutput carrying the IP and the location.
        """
        # ANTIPATTERN (deliberate, for teaching): maximum_attempts=1 disables retries so the demo
        # surfaces the first failure instead of masking it. Correct: allow retries with sensible
        # backoff in production. Do not copy.
        no_retries = RetryPolicy(maximum_attempts=1)

        ip = await workflow.execute_activity(
            get_ip,
            args=[args.block_seconds, args.mode],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
            retry_policy=no_retries,
        )
        location = await workflow.execute_activity(
            get_location,
            args=[ip, args.block_seconds, args.mode],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            schedule_to_close_timeout=ACTIVITY_SCHEDULE_TO_CLOSE_TIMEOUT,
            retry_policy=no_retries,
        )
        return GeoEnrichmentOutput(ip=ip, location=location)
