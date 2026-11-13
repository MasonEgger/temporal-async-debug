"""ABOUTME: Workflow test for GeoEnrichmentWorkflow under a time-skipping WorkflowEnvironment.
ABOUTME: The activities are stubbed, so the test touches no network and no database.
"""

from __future__ import annotations

import uuid

from shared import TASK_QUEUE, GeoEnrichmentInput, GeoEnrichmentOutput
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from workflow import GeoEnrichmentWorkflow

STUB_IP: str = "203.0.113.7"
"""Address the stubbed get_ip returns, from the RFC 5737 documentation range."""

CACHE_PATH: str = "/nonexistent/location-cache.sqlite3"
"""A cache path the stub only records; nothing opens it."""

received_cache_paths: list[str | None] = []
"""Every location_cache_path the stubbed get_location was called with."""


@activity.defn(name="get_ip")
async def get_ip_stub() -> str:
    """Stand in for get_ip, returning a fixed address without any network call."""
    return STUB_IP


@activity.defn(name="get_location")
async def get_location_stub(ip: str, location_cache_path: str | None) -> str:
    """Stand in for get_location, recording the cache path it received."""
    received_cache_paths.append(location_cache_path)
    return f"stub location for {ip}"


async def test_geo_workflow_passes_the_cache_path_through_to_get_location() -> None:
    """The workflow hands location_cache_path to get_location unchanged, along with get_ip's address."""
    received_cache_paths.clear()
    async with (
        await WorkflowEnvironment.start_time_skipping() as environment,
        Worker(
            environment.client,
            task_queue=TASK_QUEUE,
            workflows=[GeoEnrichmentWorkflow],
            activities=[get_ip_stub, get_location_stub],
        ),
    ):
        result = await environment.client.execute_workflow(
            GeoEnrichmentWorkflow.run,
            GeoEnrichmentInput(location_cache_path=CACHE_PATH),
            id=str(uuid.uuid4()),
            task_queue=TASK_QUEUE,
        )

    assert result == GeoEnrichmentOutput(ip=STUB_IP, location=f"stub location for {STUB_IP}")
    assert received_cache_paths == [CACHE_PATH]
