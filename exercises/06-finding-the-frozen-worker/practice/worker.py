"""ABOUTME: The worker that hosts every workflow type and activity for the 06-finding-the-frozen-worker exercise.
ABOUTME: Exercise 06 copy: the SDK's default activity slots and no activity_executor.

This worker is one of the two processes in the exercise's fleet; both run this file from the same
directory and poll the same task queue. It runs every async activity from all three workflow types,
and the Python side of Workflow Task handling, on a single asyncio event loop, so a blocking call in
an async activity freezes the whole worker, unrelated workflows included.

The worker enables the SDK's Prometheus metrics endpoint on 127.0.0.1, port 9464 unless
ASYNC_DEBUG_METRICS_PORT says otherwise, so a second Worker can run beside the first, and prints a
startup banner with its PID and the copy-paste commands to inspect the live event loop.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import shared
from activities import get_ip, get_location
from receipt import (
    OrderReceiptWorkflow,
    compute_total,
    format_receipt,
    validate_order,
)
from rollup import SalesRollupWorkflow, roll_up_sales
from temporalio.client import Client
from temporalio.runtime import PrometheusConfig, Runtime, TelemetryConfig
from temporalio.worker import Worker
from workflow import GeoEnrichmentWorkflow

if TYPE_CHECKING:
    from collections.abc import Mapping

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the worker connects to."""

METRICS_HOST: str = "127.0.0.1"
"""Host the SDK binds its Prometheus scrape endpoint to."""

METRICS_PORT_ENV: str = "ASYNC_DEBUG_METRICS_PORT"
"""Environment variable that overrides the metrics port, so a second Worker can run beside the first."""

DEFAULT_METRICS_PORT: int = 9464
"""Port used when ASYNC_DEBUG_METRICS_PORT is unset."""


def resolve_metrics_port(environ: Mapping[str, str] | None = None) -> int:
    """Read the Prometheus port from ASYNC_DEBUG_METRICS_PORT, defaulting to 9464.

    Args:
        environ: The environment to read; defaults to ``os.environ``.

    Returns:
        The port as an integer between 1 and 65535.

    Raises:
        ValueError: If the variable is set but empty, not an integer, or outside 1 to 65535.
    """
    env = os.environ if environ is None else environ
    raw = env.get(METRICS_PORT_ENV)
    if raw is None:
        return DEFAULT_METRICS_PORT
    try:
        port = int(raw)
    except ValueError:
        msg = f"{METRICS_PORT_ENV} must be an integer from 1 to 65535, got {raw!r}"
        raise ValueError(msg) from None
    if not 1 <= port <= 65535:
        msg = f"{METRICS_PORT_ENV} must be an integer from 1 to 65535, got {raw!r}"
        raise ValueError(msg)
    return port


def build_telemetry_config(environ: Mapping[str, str] | None = None) -> TelemetryConfig:
    """Build the telemetry config that binds the Prometheus endpoint to the resolved port.

    Args:
        environ: The environment to read the port from; defaults to ``os.environ``.

    Returns:
        A TelemetryConfig whose metrics endpoint is ``127.0.0.1:<port>``.
    """
    port = resolve_metrics_port(environ)
    return TelemetryConfig(metrics=PrometheusConfig(bind_address=f"{METRICS_HOST}:{port}"))


def print_startup_banner(metrics_port: int) -> None:
    """Print the worker's PID, the loop-introspection commands, and the metrics URL.

    The two ``python -m asyncio`` commands carry the real PID so the reader can copy-paste them
    straight into a second terminal. The metrics line shows the port the endpoint is bound to.

    Args:
        metrics_port: The port the Prometheus endpoint is bound to.
    """
    pid = os.getpid()
    # flush=True on every line: under nohup or a log redirect stdout is block-buffered, and the
    # PID would otherwise sit unwritten in the buffer while the reader needs it.
    print("=" * 72, flush=True)
    print(f"temporal-async-debug worker running with PID {pid}", flush=True)
    print("Inspect the live event loop from another terminal with either of:", flush=True)
    print(f"    python -m asyncio ps {pid}", flush=True)
    print(f"    python -m asyncio pstree {pid}", flush=True)
    print(f"Prometheus metrics: http://{METRICS_HOST}:{metrics_port}/metrics", flush=True)
    print("=" * 72, flush=True)


def build_worker(client: Client) -> Worker:
    """Construct the Worker for all three workflow types and their activities.

    Args:
        client: A connected Temporal client.

    Returns:
        The Worker, not yet running.
    """
    return Worker(
        client,
        task_queue=shared.TASK_QUEUE,
        workflows=[
            GeoEnrichmentWorkflow,
            OrderReceiptWorkflow,
            SalesRollupWorkflow,
        ],
        activities=[
            get_ip,
            get_location,
            validate_order,
            compute_total,
            format_receipt,
            roll_up_sales,
        ],
        # TODO PART D: plain def activities need somewhere to run. Give the Worker an activity_executor
        # sized to the number of activity slots.
    )


async def main() -> None:
    """Connect to the local Temporal server and run the worker.

    Builds a Runtime with the Prometheus metrics endpoint enabled, connects a Client to the
    local dev server, builds the Worker with build_worker, prints the startup banner, and then
    serves until interrupted.
    """
    telemetry = build_telemetry_config()
    runtime = Runtime(telemetry=telemetry)
    client = await Client.connect(TEMPORAL_TARGET, runtime=runtime)
    worker = build_worker(client)
    print_startup_banner(resolve_metrics_port())
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
