"""ABOUTME: GreetingWorkflow, the deliberately misbehaving workflow that runs get_ip then get_location.
ABOUTME: Short heartbeat_timeout plus maximum_attempts=1 make a frozen-loop failure surface fast.

The two activities run in sequence: get_ip fetches the public address, then get_location looks it up.
Each runs with a 60-second start_to_close_timeout and a 10-second heartbeat_timeout, so an activity
that blocks the worker's event loop stops heartbeating and times out well inside its overall budget.
The retry policy caps attempts at one on purpose (see the antipattern marker) so the first failure
reaches the caller instead of being retried and hidden.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from temporal_async_debug.activities import get_ip, get_location
    from temporal_async_debug.shared import GreetingInput, GreetingOutput

ACTIVITY_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=60)
"""Overall budget for a single activity attempt, retries excluded."""

ACTIVITY_HEARTBEAT_TIMEOUT: timedelta = timedelta(seconds=10)
"""Longest gap allowed between heartbeats; a blocked loop misses this and times out."""


@workflow.defn
class GreetingWorkflow:
    """Fetch the caller's IP, look up its location, and greet them by name.

    The workflow exists to be broken on purpose. It runs get_ip and then get_location, both of
    which can block the worker's event loop when configured to. The short heartbeat_timeout means
    a run that blocks the loop stops heartbeating and the server times the activity out within ten
    seconds, and the maximum_attempts=1 retry policy lets that first failure surface to the caller
    instead of being retried silently.
    """

    @workflow.run
    async def run(self, args: GreetingInput) -> GreetingOutput:
        """Run get_ip then get_location and assemble the greeting.

        Args:
            args: Name to greet plus the block_seconds and mode that decide whether each
                activity blocks the worker's event loop.

        Returns:
            A GreetingOutput carrying the IP, the location, and the assembled greeting.
        """
        # ANTIPATTERN (deliberate, for teaching): maximum_attempts=1 disables retries so the demo
        # surfaces the first failure instead of masking it. Correct: allow retries with sensible
        # backoff in production. Do not copy.
        no_retries = RetryPolicy(maximum_attempts=1)

        ip = await workflow.execute_activity(
            get_ip,
            args=[args.block_seconds, args.mode],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            heartbeat_timeout=ACTIVITY_HEARTBEAT_TIMEOUT,
            retry_policy=no_retries,
        )
        location = await workflow.execute_activity(
            get_location,
            args=[ip, args.block_seconds, args.mode],
            start_to_close_timeout=ACTIVITY_START_TO_CLOSE_TIMEOUT,
            heartbeat_timeout=ACTIVITY_HEARTBEAT_TIMEOUT,
            retry_policy=no_retries,
        )
        greeting = f"Hello {args.name}, you appear to be in {location}"
        return GreetingOutput(ip=ip, location=location, greeting=greeting)
