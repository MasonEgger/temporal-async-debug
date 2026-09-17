"""ABOUTME: Workflow tests for GreetingWorkflow under a time-skipping WorkflowEnvironment.
ABOUTME: Activities are stubbed to return fixed strings, so no test touches the network.

The happy path proves the two-activity sequence and the greeting shape; the stubbed get_location
asserts it received the ip that get_ip produced, which pins the ordering. The error path proves
maximum_attempts=1 surfaces the first failure as a WorkflowFailureError instead of retrying it away.
"""

from __future__ import annotations

import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal_async_debug.shared import TASK_QUEUE, GreetingInput, GreetingOutput
from temporal_async_debug.workflow import GreetingWorkflow

STUB_IP: str = "203.0.113.7"
"""Address the stubbed get_ip returns, from the RFC 5737 documentation range."""

STUB_LOCATION: str = "Austin, Texas, United States"
"""Location the stubbed get_location returns once it has confirmed the ip."""

GET_IP_FAILURE_MESSAGE: str = "stubbed get_ip failure"
"""Message the failing get_ip stub raises, checked in the error-path cause chain."""


@activity.defn(name="get_ip")
async def get_ip_stub(block_seconds: float, mode: str) -> str:
    """Stand in for get_ip, returning a fixed address without any network call."""
    return STUB_IP


@activity.defn(name="get_location")
async def get_location_stub(ip: str, block_seconds: float, mode: str) -> str:
    """Stand in for get_location, asserting it received the ip that get_ip produced first."""
    assert ip == STUB_IP
    return STUB_LOCATION


async def test_greeting_workflow_happy_path_returns_greeting_with_name() -> None:
    """The workflow runs get_ip then get_location and greets the caller by name."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[GreetingWorkflow],
            activities=[get_ip_stub, get_location_stub],
        ),
    ):
        result = await env.client.execute_workflow(
            GreetingWorkflow.run,
            GreetingInput(name="friend", block_seconds=0.0, mode="block"),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, GreetingOutput)
    assert result.ip == STUB_IP
    assert result.location == STUB_LOCATION
    assert "friend" in result.greeting


async def test_greeting_workflow_surfaces_first_failure_without_retrying() -> None:
    """maximum_attempts=1 fails the workflow on the first get_ip error instead of retrying."""
    attempts: list[int] = []
    """Attempt numbers the failing stub saw, one entry per invocation; proves no retry."""

    @activity.defn(name="get_ip")
    async def get_ip_failing(block_seconds: float, mode: str) -> str:
        """Stand in for get_ip that always fails, recording each attempt to prove no retry."""
        attempts.append(activity.info().attempt)
        raise ApplicationError(GET_IP_FAILURE_MESSAGE)

    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[GreetingWorkflow],
            activities=[get_ip_failing, get_location_stub],
        ),
    ):
        with pytest.raises(WorkflowFailureError) as failure:
            await env.client.execute_workflow(
                GreetingWorkflow.run,
                GreetingInput(name="friend"),
                id=str(uuid.uuid4()),
                task_queue=TASK_QUEUE,
            )

    # Exactly one attempt: maximum_attempts=1 disabled the retry that would append a second entry.
    # Bumping the workflow's RetryPolicy to maximum_attempts=2 makes this list [1, 2] and fails here.
    assert attempts == [1]

    # The failure is the stubbed error surfaced through the activity, not a start_to_close timeout.
    activity_error = failure.value.cause
    assert isinstance(activity_error, ActivityError)
    application_error = activity_error.cause
    assert isinstance(application_error, ApplicationError)
    assert GET_IP_FAILURE_MESSAGE in str(application_error)
