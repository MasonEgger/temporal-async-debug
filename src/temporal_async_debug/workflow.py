"""ABOUTME: GeoEnrichmentWorkflow, which runs get_ip then get_location to enrich a caller's address.
ABOUTME: geo_activity_options(mode) selects each mode's timeouts so every failure signature fires correctly.

Both activities share one generous start_to_close_timeout (120 seconds) regardless of mode. An
awaiting activity is cancelled by the SDK at start_to_close (live-verified), so "slow" and
"slow_heartbeat" need that generous budget to hold their activity slot for the full delay instead
of being cut off partway through; "block" and "cpu" get the same budget even though they freeze
the loop instead of awaiting, since they are diagnosed from the frozen stack trace, not a timeout.
"slow_heartbeat" and "stuck_no_heartbeat" also carry a 10-second heartbeat_timeout: "slow_heartbeat"
satisfies it every step and runs to completion (the correct way to hold a slot for long work), while
"stuck_no_heartbeat" never heartbeats and is cancelled by the missing heartbeat instead of by
start_to_close. The retry policy caps attempts at one on purpose (see the antipattern marker) so
the first failure reaches the caller instead of being retried and hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TypedDict

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from temporal_async_debug.activities import get_ip, get_location
    from temporal_async_debug.shared import VALID_MODES, GeoEnrichmentInput, GeoEnrichmentOutput

GEO_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=120)
"""Budget for a single activity attempt, generous enough to hold a slot through the full delay of
the "slow" and "slow_heartbeat" modes."""

GEO_SCHEDULE_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=150)
"""Overall budget from schedule to close; queued work breaches this when the worker is jammed."""

GEO_HEARTBEAT_TIMEOUT: timedelta = timedelta(seconds=10)
"""Heartbeat interval "slow_heartbeat" satisfies every step and "stuck_no_heartbeat" never does."""

_MODES_REQUIRING_HEARTBEAT: frozenset[str] = frozenset({"slow_heartbeat", "stuck_no_heartbeat"})
"""The only two modes whose options carry a heartbeat_timeout."""


@dataclass(frozen=True)
class GeoActivityOptions:
    """Per-mode activity execution options shared by GeoEnrichmentWorkflow and its tests.

    Attributes:
        start_to_close_timeout: Budget for a single get_ip or get_location attempt.
        schedule_to_close_timeout: Overall budget from schedule to close.
        heartbeat_timeout: Interval the activity must heartbeat within, or None when the mode
            neither heartbeats nor needs to be caught by a missing one.
        retry_policy: Retry policy every mode shares; see the antipattern marker in
            geo_activity_options.
    """

    start_to_close_timeout: timedelta
    schedule_to_close_timeout: timedelta
    heartbeat_timeout: timedelta | None
    retry_policy: RetryPolicy


class _ActivityExecutionKwargs(TypedDict, total=False):
    """The subset of workflow.execute_activity keyword arguments geo options fill in.

    heartbeat_timeout is the only key ever omitted, for modes whose options carry none.
    """

    start_to_close_timeout: timedelta
    schedule_to_close_timeout: timedelta
    heartbeat_timeout: timedelta
    retry_policy: RetryPolicy


def geo_activity_options(mode: str) -> GeoActivityOptions:
    """Return the activity options GeoEnrichmentWorkflow uses to run get_ip and get_location.

    Every mode gets the same generous start_to_close and schedule_to_close budgets, per the live-
    verified mechanic that an awaiting activity is cancelled at start_to_close: "slow" and
    "slow_heartbeat" need the full 120 seconds to hold their slot for the whole delay, and "block"
    and "cpu" get the same budget even though a frozen loop is diagnosed from its stack, not a
    timeout. "slow_heartbeat" and "stuck_no_heartbeat" additionally carry a heartbeat_timeout:
    "slow_heartbeat" satisfies it every step (the correct way to hold a slot for legitimate long
    work), while "stuck_no_heartbeat" never heartbeats and is cancelled by the missing heartbeat
    rather than by start_to_close. "slow" is cooperative but silent, so it carries none.

    Args:
        mode: One of shared.VALID_MODES.

    Returns:
        The GeoActivityOptions for that mode.

    Raises:
        ValueError: If mode is not one of shared.VALID_MODES.
    """
    if mode not in VALID_MODES:
        raise ValueError(f"unknown mode: {mode!r}; expected one of {VALID_MODES}")

    heartbeat_timeout = GEO_HEARTBEAT_TIMEOUT if mode in _MODES_REQUIRING_HEARTBEAT else None

    return GeoActivityOptions(
        start_to_close_timeout=GEO_START_TO_CLOSE_TIMEOUT,
        schedule_to_close_timeout=GEO_SCHEDULE_TO_CLOSE_TIMEOUT,
        heartbeat_timeout=heartbeat_timeout,
        # ANTIPATTERN (deliberate, for teaching): maximum_attempts=1 looks like exactly-once but
        # is at-most-one dispatch: a transient failure before the call means it never runs and the
        # Workflow fails, and a Worker that finishes the side effect but crashes before recording
        # completion leaves the effect done while the Workflow sees a failure. Correct: keep
        # retries (Activities are at-least-once) and make the Activity idempotent with a stable
        # key such as workflow_run_id plus activity_id for effectively-once side effects; cap
        # attempts only when a duplicate is worse than a loss and the loss is handled. Set here
        # only so the demo surfaces the first failure instead of retrying past it. Do not copy.
        retry_policy=RetryPolicy(maximum_attempts=1),
    )


def _activity_execution_kwargs(options: GeoActivityOptions) -> _ActivityExecutionKwargs:
    """Build workflow.execute_activity keyword arguments from options, omitting a None heartbeat.

    Args:
        options: The per-mode options returned by geo_activity_options.

    Returns:
        Keyword arguments for workflow.execute_activity, with heartbeat_timeout present only
        when options.heartbeat_timeout is not None.
    """
    kwargs: _ActivityExecutionKwargs = {
        "start_to_close_timeout": options.start_to_close_timeout,
        "schedule_to_close_timeout": options.schedule_to_close_timeout,
        "retry_policy": options.retry_policy,
    }
    if options.heartbeat_timeout is not None:
        kwargs["heartbeat_timeout"] = options.heartbeat_timeout
    return kwargs


@workflow.defn
class GeoEnrichmentWorkflow:
    """Fetch the caller's IP and look up its location.

    The workflow runs get_ip and then get_location, both of which can block the worker's event
    loop or hold an activity slot when their input asks them to. geo_activity_options(args.mode)
    selects each mode's timeouts. The maximum_attempts=1 retry policy it returns lets the first
    failure surface to the caller instead of being retried past; it is at-most-one dispatch, not
    exactly-once, so production code keeps retries and makes the Activity idempotent instead.
    """

    @workflow.run
    async def run(self, args: GeoEnrichmentInput) -> GeoEnrichmentOutput:
        """Run get_ip then get_location and return the enriched address.

        Args:
            args: The block_seconds and mode that decide whether each activity blocks the
                worker's event loop or holds its slot, and which timeouts apply.

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
        activity_kwargs = _activity_execution_kwargs(options)

        ip = await workflow.execute_activity(
            get_ip,
            args=[args.block_seconds, args.mode],
            **activity_kwargs,
        )
        location = await workflow.execute_activity(
            get_location,
            args=[ip, args.block_seconds, args.mode],
            **activity_kwargs,
        )
        return GeoEnrichmentOutput(ip=ip, location=location)
