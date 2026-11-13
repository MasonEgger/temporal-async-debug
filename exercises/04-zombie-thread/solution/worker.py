"""ABOUTME: The worker that hosts every workflow type and activity for the 04-zombie-thread exercise.
ABOUTME: Exercise 04 copy: get_location is a plain def on a ThreadPoolExecutor sized to the slots, and it heartbeats.

This worker is the process the exercise attaches to and inspects. get_location is a plain ``def``
function, so it runs on the ``activity_executor`` below, a thread pool with one thread per activity
slot. It heartbeats between steps from its own thread, so a timeout or cancel arrives as
``CancelledError`` inside that thread and the work stops. The pool is sized to
``MAX_CONCURRENT_ACTIVITIES`` because the Worker hands the executor as many tasks as it has slots,
whether or not a thread is free. The event loop that runs the poller, the heartbeat sender, and the async
receipt and rollup activities stays live.

``MAX_CONCURRENT_ACTIVITIES`` is small on purpose, so the slot gauge readings stay short enough to
read on a single machine.

The worker enables the SDK's Prometheus metrics endpoint on 127.0.0.1:9464 and prints a startup
banner with its PID and the copy-paste commands to inspect the live event loop.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

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

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the worker connects to."""

METRICS_BIND_ADDRESS: str = "127.0.0.1:9464"
"""Host and port the SDK binds its Prometheus scrape endpoint to."""

METRICS_URL: str = "http://127.0.0.1:9464/metrics"
"""Full URL a browser or curl uses to read the worker's metrics."""

MAX_CONCURRENT_ACTIVITIES: int = 2
"""Small on purpose: a single-machine demo keeps the slot gauge readings short and readable."""


def print_startup_banner() -> None:
    """Print the worker's PID, the loop-introspection commands, and the metrics URL.

    The two ``python -m asyncio`` commands carry the real PID so the reader can copy-paste them
    straight into a second terminal.
    """
    pid = os.getpid()
    # flush=True on every line: under nohup or a log redirect stdout is block-buffered, and the
    # PID would otherwise sit unwritten in the buffer while the reader needs it.
    print("=" * 72, flush=True)
    print(f"temporal-async-debug worker running with PID {pid}", flush=True)
    print("Inspect the live event loop from another terminal with either of:", flush=True)
    print(f"    python -m asyncio ps {pid}", flush=True)
    print(f"    python -m asyncio pstree {pid}", flush=True)
    print(f"Prometheus metrics: {METRICS_URL}", flush=True)
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
        activity_executor=ThreadPoolExecutor(max_workers=MAX_CONCURRENT_ACTIVITIES),
        max_concurrent_activities=MAX_CONCURRENT_ACTIVITIES,
    )


async def main() -> None:
    """Connect to the local Temporal server and run the worker.

    Builds a Runtime with the Prometheus metrics endpoint enabled, connects a Client to the
    local dev server, builds the Worker with build_worker, prints the startup banner, and then
    serves until interrupted.
    """
    runtime = Runtime(
        telemetry=TelemetryConfig(
            metrics=PrometheusConfig(bind_address=METRICS_BIND_ADDRESS),
        ),
    )
    client = await Client.connect(TEMPORAL_TARGET, runtime=runtime)
    worker = build_worker(client)
    print_startup_banner()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
