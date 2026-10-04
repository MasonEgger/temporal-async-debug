"""ABOUTME: A test helper that reads the ActivityTaskScheduled events out of a finished workflow's history.
ABOUTME: Lets workflow tests assert the timeouts the server actually received, not just what a helper computed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temporalio.api.history.v1 import ActivityTaskScheduledEventAttributes
    from temporalio.client import WorkflowHandle


async def scheduled_activity_attributes[WorkflowT, ResultT](
    handle: WorkflowHandle[WorkflowT, ResultT],
) -> list[ActivityTaskScheduledEventAttributes]:
    """Return the ActivityTaskScheduled attributes from a workflow's history, in schedule order.

    Asserting these attributes is the offline-safe way to prove a workflow passes its timeouts
    through to execute_activity; tripping a timeout like schedule_to_start under time-skipping is
    not reliable.

    Args:
        handle: A handle to a workflow that has already run.

    Returns:
        One ActivityTaskScheduledEventAttributes per activity the workflow scheduled.
    """
    history = await handle.fetch_history()
    return [
        event.activity_task_scheduled_event_attributes
        for event in history.events
        if event.HasField("activity_task_scheduled_event_attributes")
    ]
