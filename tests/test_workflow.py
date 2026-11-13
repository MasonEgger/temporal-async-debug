"""ABOUTME: Workflow tests for GeoEnrichmentWorkflow under a time-skipping WorkflowEnvironment.
ABOUTME: Activities are stubbed to return fixed strings, so no test touches the network.

The happy path proves the two-activity sequence and the output shape; the stubbed get_location
asserts it received the ip that get_ip produced, which pins the ordering. The error path proves
the unknown-mode path fails the run with an ApplicationError instead of stalling it.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from temporal_async_debug.shared import TASK_QUEUE, GeoEnrichmentInput, GeoEnrichmentOutput
from temporal_async_debug.workflow import GeoEnrichmentWorkflow
from tests.history import scheduled_activity_attributes

STUB_IP: str = "203.0.113.7"
"""Address the stubbed get_ip returns, from the RFC 5737 documentation range."""

STUB_LOCATION: str = "Austin, Texas, United States"
"""Location the stubbed get_location returns once it has confirmed the ip."""


@activity.defn(name="get_ip")
async def get_ip_stub(block_seconds: float, mode: str) -> str:
    """Stand in for get_ip, returning a fixed address without any network call."""
    return STUB_IP


@activity.defn(name="get_location")
async def get_location_stub(ip: str, block_seconds: float, mode: str) -> str:
    """Stand in for get_location, asserting it received the ip that get_ip produced first."""
    assert ip == STUB_IP
    return STUB_LOCATION


async def test_geo_workflow_happy_path_returns_ip_and_location() -> None:
    """The workflow runs get_ip then get_location and returns both results."""
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[GeoEnrichmentWorkflow],
            activities=[get_ip_stub, get_location_stub],
        ),
    ):
        result = await env.client.execute_workflow(
            GeoEnrichmentWorkflow.run,
            GeoEnrichmentInput(block_seconds=0.0, mode="block"),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, GeoEnrichmentOutput)
    assert result.ip == STUB_IP
    assert result.location == STUB_LOCATION


@pytest.mark.parametrize("mode", ["block", "cpu"])
async def test_geo_workflow_passes_its_timeouts_through_to_the_scheduled_activities(mode: str) -> None:
    """Both scheduled geo activities carry the fixed timeouts, read back from the server's history.

    A zero heartbeat_timeout in the history is how the server records "none set".
    """
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[GeoEnrichmentWorkflow],
            activities=[get_ip_stub, get_location_stub],
        ),
    ):
        handle = await env.client.start_workflow(
            GeoEnrichmentWorkflow.run,
            GeoEnrichmentInput(block_seconds=0.0, mode=mode),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )
        await handle.result()
        scheduled = await scheduled_activity_attributes(handle)

    assert [attributes.activity_type.name for attributes in scheduled] == ["get_ip", "get_location"]
    for attributes in scheduled:
        assert attributes.heartbeat_timeout.ToTimedelta() == timedelta(0)
        assert attributes.start_to_close_timeout.ToTimedelta() == timedelta(seconds=120)
        assert attributes.schedule_to_close_timeout.ToTimedelta() == timedelta(seconds=150)


async def test_geo_workflow_fails_fast_on_an_unknown_mode() -> None:
    """An unknown mode fails the run with an ApplicationError of type InvalidMode instead of stalling it.

    A plain ValueError raised in workflow code would fail the workflow task and retry it forever.
    """
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[GeoEnrichmentWorkflow],
            activities=[get_ip_stub, get_location_stub],
        ),
    ):
        with pytest.raises(WorkflowFailureError) as failure:
            await env.client.execute_workflow(
                GeoEnrichmentWorkflow.run,
                GeoEnrichmentInput(block_seconds=0.0, mode="sideways"),
                id=str(uuid.uuid4()),
                task_queue=TASK_QUEUE,
                # Bounds the stall a retrying workflow task would cause, so a regression fails here.
                execution_timeout=timedelta(minutes=1),
            )

    application_error = failure.value.cause
    assert isinstance(application_error, ApplicationError)
    assert application_error.type == "InvalidMode"
    assert "unknown mode" in str(application_error)
