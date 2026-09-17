"""ABOUTME: VictimWorkflow and quick_task, the correct code that shares the misbehaving worker.
ABOUTME: Nothing here is broken; it is the contrast the tutorial points at when the loop freezes.

quick_task does no network and returns immediately, so the victim workflow is fast and correct in
every respect. Its one deliberate oddity is a short schedule_to_start_timeout (see the antipattern
marker), set only so that when the misbehaving worker's slots are exhausted the victim's activity
times out fast and visibly instead of waiting silently.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from temporal_async_debug.shared import VictimInput, VictimOutput

QUICK_TASK_START_TO_CLOSE_TIMEOUT: timedelta = timedelta(seconds=10)
"""Overall budget for a single quick_task attempt; generous since the task is trivial."""

# ANTIPATTERN (deliberate, for teaching): a short schedule_to_start_timeout is normally an
# antipattern; it is set here only to make slot exhaustion fail fast and visibly. Correct:
# usually leave schedule_to_start unset and size the worker to demand. Do not copy.
QUICK_TASK_SCHEDULE_TO_START_TIMEOUT: timedelta = timedelta(seconds=10)
"""Longest an activity task may sit queued before starting; short so exhaustion times out fast."""


@activity.defn
async def quick_task(label: str) -> str:
    """Return a fast, computed result for the given label with no sleep and no network.

    This activity is deliberately correct and cheap; it exists so the victim workflow has real
    work to do that should always succeed when the worker has a free slot.

    Args:
        label: Identifier that distinguishes one victim run from another.

    Returns:
        A short confirmation string of the form ``processed {label}``.
    """
    return f"processed {label}"


@workflow.defn
class VictimWorkflow:
    """Run one quick, correct activity and return a message confirming it completed.

    VictimWorkflow is the innocent bystander in the demo. It shares a worker with the misbehaving
    GreetingWorkflow, and it is written correctly on purpose so that any failure it suffers is
    clearly caused by the worker being starved or its slots exhausted, not by its own code.
    """

    @workflow.run
    async def run(self, args: VictimInput) -> VictimOutput:
        """Execute quick_task and wrap its result in a VictimOutput.

        Args:
            args: The label identifying this victim run.

        Returns:
            A VictimOutput whose message carries the label and the quick_task result.
        """
        result = await workflow.execute_activity(
            quick_task,
            args=[args.label],
            start_to_close_timeout=QUICK_TASK_START_TO_CLOSE_TIMEOUT,
            schedule_to_start_timeout=QUICK_TASK_SCHEDULE_TO_START_TIMEOUT,
        )
        return VictimOutput(message=f"victim {args.label}: {result}")
