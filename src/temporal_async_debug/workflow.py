"""ABOUTME: GeoEnrichmentWorkflow, which runs get_ip then get_location to enrich a caller's address.
ABOUTME: geo_activity_options(mode) validates the mode and returns the one fixed set of timeouts.

Both activities share one generous start_to_close_timeout (120 seconds) and a 150-second
schedule_to_close_timeout regardless of mode. The frozen-loop modes ("block" and "cpu") are diagnosed
from the frozen stack, not from a timeout, so the budgets stay wide. There is no heartbeat_timeout and
no custom retry policy: the geo activities use the Temporal default, like every other activity here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from temporal_async_debug.activities import get_ip, get_location
    from temporal_async_debug.shared import VALID_MODES, GeoEnrichmentInput, GeoEnrichmentOutput

GEO_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=120)
"""Budget for a single activity attempt, generous enough that a long freeze is not cut off."""

GEO_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=150)
"""Overall budget from schedule to close."""


@dataclass(frozen=True)
class GeoActivityOptions:
    """Activity execution options shared by GeoEnrichmentWorkflow and its tests.

    Attributes:
        start_to_close_timeout: Budget for a single get_ip or get_location attempt.
        schedule_to_close_timeout: Overall budget from schedule to close.
    """

    start_to_close_timeout: timedelta
    schedule_to_close_timeout: timedelta


def geo_activity_options(mode: str) -> GeoActivityOptions:
    """Return the activity options GeoEnrichmentWorkflow uses to run get_ip and get_location.

    Every valid mode gets the same fixed budgets.

    Args:
        mode: One of shared.VALID_MODES.

    Returns:
        The GeoActivityOptions, the same for every valid mode.

    Raises:
        ValueError: If mode is not one of shared.VALID_MODES.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode: {mode!r}; expected one of {VALID_MODES}")

    return GeoActivityOptions(
        start_to_close_timeout=GEO_START_TO_CLOSE_TIMEOUT,
        schedule_to_close_timeout=GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
    )


@workflow.defn
class GeoEnrichmentWorkflow:
    """Fetch the caller's IP and look up its location.

    The workflow runs get_ip and then get_location, both of which can freeze the worker's event
    loop when their input asks them to. geo_activity_options(args.mode) validates the mode and
    supplies the fixed timeouts; the activities use the default retry policy.
    """

    @workflow.run
    async def run(self, args: GeoEnrichmentInput) -> GeoEnrichmentOutput:
        """Run get_ip then get_location and return the enriched address.

        Args:
            args: The block_seconds and mode that decide whether and how each activity freezes
                the worker's event loop.

        Returns:
            A GeoEnrichmentOutput carrying the IP and the location.

        Raises:
            ApplicationError: Of type "InvalidMode", if args.mode is not one of shared.VALID_MODES.
                A plain ValueError raised in workflow code fails only the workflow task, which the
                worker retries forever and the run stalls; an ApplicationError fails the run
                itself, so the caller sees the bad input at once.
        """
        try:
            options = geo_activity_options(args.mode)
        except ValueError as invalid_mode:
            raise ApplicationError(str(invalid_mode), type="InvalidMode") from invalid_mode

        ip = await workflow.execute_activity(
            get_ip,
            args=[args.block_seconds, args.mode],
            start_to_close_timeout=options.start_to_close_timeout,
            schedule_to_close_timeout=options.schedule_to_close_timeout,
        )
        location = await workflow.execute_activity(
            get_location,
            args=[ip, args.block_seconds, args.mode],
            start_to_close_timeout=options.start_to_close_timeout,
            schedule_to_close_timeout=options.schedule_to_close_timeout,
        )
        return GeoEnrichmentOutput(ip=ip, location=location)
