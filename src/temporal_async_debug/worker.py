"""ABOUTME: The deliberately mistuned worker that hosts every demo workflow type and activity.
ABOUTME: max_concurrent_activities=2 with no executor lets two blocking activities stall the queue.

This worker is the process the tutorial attaches to and inspects. It runs its poller, its heartbeat
sender, and every async activity from all four workflow types on a single asyncio event loop, so the
blocking bug in activities.py freezes the whole worker, unrelated workflows included. Two deliberate
choices make the failure legible:

- ``max_concurrent_activities=2`` undersizes the slot pool so a pair of slow or blocked activities
  exhausts every slot and the other work on the worker starves.
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
from temporal_async_debug.quote import PriceQuoteWorkflow, compute_quote
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
    print("=" * 72)
    print(f"temporal-async-debug worker running with PID {pid}")
    print("Inspect the live event loop from another terminal with either of:")
    print(f"    python -m asyncio ps {pid}")
    print(f"    python -m asyncio pstree {pid}")
    print(f"Prometheus metrics: {METRICS_URL}")
    print("=" * 72)


async def main() -> None:
    """Connect to the local Temporal server and run the deliberately mistuned worker.

    Builds a Runtime with the Prometheus metrics endpoint enabled, connects a Client to the
    local dev server, constructs the Worker for all four workflow types and their activities,
    prints the startup banner, and then serves until interrupted.
    """
    runtime = Runtime(
        telemetry=TelemetryConfig(
            metrics=PrometheusConfig(bind_address=METRICS_BIND_ADDRESS),
        ),
    )
    client = await Client.connect(TEMPORAL_TARGET, runtime=runtime)
    worker = Worker(
        client,
        task_queue=shared.TASK_QUEUE,
        workflows=[
            GeoEnrichmentWorkflow,
            OrderReceiptWorkflow,
            SalesRollupWorkflow,
            PriceQuoteWorkflow,
        ],
        activities=[
            get_ip,
            get_location,
            validate_order,
            compute_total,
            format_receipt,
            roll_up_sales,
            compute_quote,
        ],
        # ANTIPATTERN (deliberate, for teaching): max_concurrent_activities=2 undersizes the
        # worker so two slow activities exhaust every slot and stall the queue. Correct: size
        # slots to expected concurrency and load. Do not copy.
        max_concurrent_activities=2,
    )
    print_startup_banner()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
