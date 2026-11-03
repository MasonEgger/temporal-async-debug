"""ABOUTME: The worker that hosts every demo workflow type and activity on one event loop.
ABOUTME: max_concurrent_activities=2 and no executor keep the freeze lessons small and readable.

This worker is the process the tutorial attaches to and inspects. It runs its poller, its heartbeat
sender, and every async activity from all three workflow types on a single asyncio event loop, so the
blocking bug in activities.py freezes the whole worker, unrelated workflows included.

- ``max_concurrent_activities=2`` is small on purpose, so the slot gauge readings in the lessons stay
  short enough to read on a single machine.
- No ``activity_executor`` means the activities run on the event loop itself rather than in a thread
  or process pool, which is exactly what lets ``time.sleep`` freeze the loop.

The worker enables the SDK's Prometheus metrics endpoint on 127.0.0.1:9464 and prints a startup
banner with its PID and the copy-paste commands to inspect the live event loop.
"""

from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.runtime import PrometheusConfig, Runtime, TelemetryConfig
from temporalio.worker import Worker

from temporal_async_debug import shared
from temporal_async_debug.activities import get_ip, get_location
from temporal_async_debug.receipt import (
    OrderReceiptWorkflow,
    compute_total,
    format_receipt,
    validate_order,
)
from temporal_async_debug.rollup import SalesRollupWorkflow, roll_up_sales
from temporal_async_debug.workflow import GeoEnrichmentWorkflow

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the worker connects to."""

METRICS_BIND_ADDRESS: str = "127.0.0.1:9464"
"""Host and port the SDK binds its Prometheus scrape endpoint to."""

METRICS_URL: str = "http://127.0.0.1:9464/metrics"
"""Full URL a browser or curl uses to read the worker's metrics."""


def print_startup_banner() -> None:
    """Print the worker's PID, the loop-introspection commands, and the metrics URL.

    Kept import-safe and free of any client or server dependency so it can be called
    (or tested) without connecting to Temporal. The two ``python -m asyncio`` commands
    carry the real PID so the reader can copy-paste them straight into a second terminal.
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

    Kept free of any connection logic so tests can build it against a test environment's client
    and inspect its configuration without polling a real server.

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
        # Small on purpose: a single-machine demo keeps the slot gauge readings short and readable.
        max_concurrent_activities=2,
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
