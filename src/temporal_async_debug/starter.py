"""ABOUTME: The CLI that submits a fleet of geo-enrichment and order-receipt workflows to the worker.
ABOUTME: Parsing and input construction are pure functions so they unit-test without a server.

The starter submits a mixed fleet so the reader can watch one workflow type take down another:

- ``--mode``: how a bad geo-enrichment run delays, "block" (freezes the worker's event loop) or
  "slow" (a cooperative await that still holds an activity slot). Defaults to "block".
- ``--block-seconds``: seconds of delay each bad geo activity applies. Defaults to 0.0.
- ``--bad``: how many geo-enrichment runs to submit in the bad mode. Defaults to 0.
- ``--geo``: how many healthy geo-enrichment runs to submit alongside. Defaults to 0.
- ``--receipts``: how many order-receipt runs to submit alongside. Defaults to 0.

When a run has bad geo workflows and any bystanders, the starter sequences submission so the failure
is never a race. It submits the bad geo workflows first, watches the metrics endpoint until the
activity slot gauge shows the slots are taken, and only then submits the bystanders, which therefore
hit the frozen loop or the full slot pool every run. Nothing here is labeled a victim; the reader
finds the cause from the tooling, not from a name.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import uuid
from typing import TYPE_CHECKING

import httpx
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle

from temporal_async_debug.receipt import OrderReceiptWorkflow
from temporal_async_debug.shared import TASK_QUEUE, GeoEnrichmentInput, OrderReceiptInput
from temporal_async_debug.workflow import GeoEnrichmentWorkflow

if TYPE_CHECKING:
    from temporal_async_debug.shared import GeoEnrichmentOutput, OrderReceiptOutput

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the starter submits to."""

METRICS_URL: str = "http://127.0.0.1:9464/metrics"
"""Where the worker exports Prometheus metrics, including the activity slot gauge."""

METRICS_TIMEOUT_SECONDS: float = 3.0
"""Per-request timeout when scraping the metrics endpoint."""

SLOT_POLL_TIMEOUT_SECONDS: float = 20.0
"""How long to wait for the bad geo activities to take every slot before submitting bystanders anyway."""

SLOT_POLL_INTERVAL_SECONDS: float = 0.5
"""How often to re-scrape the slot gauge while waiting for the slots to fill."""

_ACTIVITY_SLOTS_PATTERN = re.compile(
    r'temporal_worker_task_slots_available\{[^}]*worker_type="ActivityWorker"[^}]*\}\s+([0-9.]+)'
)
"""Matches the ActivityWorker free-slot gauge line, avoiding the LocalActivityWorker line."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the starter CLI.

    Returns:
        An ArgumentParser defining --mode, --block-seconds, --bad, --geo, and --receipts
        with the demo's healthy defaults.
    """
    parser = argparse.ArgumentParser(
        prog="temporal-async-debug",
        description="Submit a fleet of geo-enrichment and order-receipt workflows to the demo worker.",
    )
    parser.add_argument(
        "--mode",
        choices=["block", "slow"],
        default="block",
        help="How a bad geo run delays: block freezes the event loop, slow awaits cooperatively.",
    )
    parser.add_argument(
        "--block-seconds",
        type=float,
        default=0.0,
        help="Seconds of delay each bad geo activity applies before its HTTP call.",
    )
    parser.add_argument(
        "--bad",
        type=int,
        default=0,
        help="How many geo-enrichment runs to submit in the bad mode.",
    )
    parser.add_argument(
        "--geo",
        type=int,
        default=0,
        help="How many healthy geo-enrichment runs to submit alongside.",
    )
    parser.add_argument(
        "--receipts",
        type=int,
        default=0,
        help="How many order-receipt runs to submit alongside.",
    )
    return parser


def bad_geo_inputs_from_args(args: argparse.Namespace) -> list[GeoEnrichmentInput]:
    """Build one GeoEnrichmentInput per bad geo run, each carrying the bad mode and delay.

    Args:
        args: Parsed CLI arguments carrying bad, block_seconds, and mode.

    Returns:
        A list of ``args.bad`` GeoEnrichmentInput values in the bad mode.
    """
    return [GeoEnrichmentInput(block_seconds=args.block_seconds, mode=args.mode) for _ in range(args.bad)]


def healthy_geo_inputs_from_args(args: argparse.Namespace) -> list[GeoEnrichmentInput]:
    """Build one healthy GeoEnrichmentInput per requested healthy geo run.

    Args:
        args: Parsed CLI arguments carrying the geo count.

    Returns:
        A list of ``args.geo`` GeoEnrichmentInput values with no delay.
    """
    return [GeoEnrichmentInput(block_seconds=0.0, mode="block") for _ in range(args.geo)]


def receipt_inputs_from_args(args: argparse.Namespace) -> list[OrderReceiptInput]:
    """Build one OrderReceiptInput per requested receipt run, each with a distinct order id.

    Args:
        args: Parsed CLI arguments carrying the receipts count.

    Returns:
        A list of ``args.receipts`` OrderReceiptInput values with distinct order ids.
    """
    return [
        OrderReceiptInput(order_id=f"order-{run_index}", item_count=3, unit_price_cents=1999)
        for run_index in range(args.receipts)
    ]


def parse_activity_slots_available(metrics_text: str) -> int | None:
    """Read the ActivityWorker free-slot gauge out of a Prometheus metrics page.

    Args:
        metrics_text: The body of the worker's /metrics endpoint.

    Returns:
        The number of free activity slots, or None when the gauge is not present yet, for example
        before the worker has finished starting.
    """
    match = _ACTIVITY_SLOTS_PATTERN.search(metrics_text)
    if match is None:
        return None
    return int(float(match.group(1)))


async def wait_for_free_activity_slots(target_free: int) -> bool:
    """Poll the worker's metrics endpoint until free activity slots fall to target_free.

    Args:
        target_free: The free-slot count to wait for, for example 0 once the bad geo runs hold
            every slot.

    Returns:
        True if the target was reached within SLOT_POLL_TIMEOUT_SECONDS, False if it timed out.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SLOT_POLL_TIMEOUT_SECONDS
    async with httpx.AsyncClient(timeout=METRICS_TIMEOUT_SECONDS) as http_client:
        while loop.time() < deadline:
            try:
                response = await http_client.get(METRICS_URL)
                free_slots = parse_activity_slots_available(response.text)
            except httpx.HTTPError:
                free_slots = None
            if free_slots is not None and free_slots <= target_free:
                return True
            await asyncio.sleep(SLOT_POLL_INTERVAL_SECONDS)
    return False


async def _read_free_activity_slots() -> int | None:
    """Scrape the metrics endpoint once and return the current free activity slot count."""
    async with httpx.AsyncClient(timeout=METRICS_TIMEOUT_SECONDS) as http_client:
        try:
            response = await http_client.get(METRICS_URL)
        except httpx.HTTPError:
            return None
    return parse_activity_slots_available(response.text)


async def _report_results[WorkflowT, ResultT](label: str, handles: list[WorkflowHandle[WorkflowT, ResultT]]) -> None:
    """Await each workflow handle and print its result, or its failure if it timed out.

    Args:
        label: A short word naming the batch, "geo" or "receipt", for the printed lines.
        handles: The started workflow handles to await in order.
    """
    for handle in handles:
        try:
            result = await handle.result()
        except WorkflowFailureError as failure:
            print(f"{label} {handle.id} FAILED: {failure.cause}")
        else:
            print(f"{label} {handle.id}: {result}")


async def _start_geo(
    client: Client,
    inputs: list[GeoEnrichmentInput],
) -> list[WorkflowHandle[GeoEnrichmentWorkflow, GeoEnrichmentOutput]]:
    """Start one GeoEnrichmentWorkflow per input and return the handles without awaiting them."""
    return [
        await client.start_workflow(
            GeoEnrichmentWorkflow.run,
            geo_input,
            id=f"geo-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        for geo_input in inputs
    ]


async def _start_receipts(
    client: Client,
    inputs: list[OrderReceiptInput],
) -> list[WorkflowHandle[OrderReceiptWorkflow, OrderReceiptOutput]]:
    """Start one OrderReceiptWorkflow per input and return the handles without awaiting them."""
    return [
        await client.start_workflow(
            OrderReceiptWorkflow.run,
            receipt_input,
            id=f"receipt-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        for receipt_input in inputs
    ]


async def _run_fleet_with_sequencing(
    client: Client,
    bad_geo_inputs: list[GeoEnrichmentInput],
    healthy_geo_inputs: list[GeoEnrichmentInput],
    receipt_inputs: list[OrderReceiptInput],
) -> None:
    """Submit the bad geo runs first, wait until they hold the slots, then submit the bystanders.

    Starting the bad runs first and confirming the slots are gone before the bystanders arrive is
    what turns the failure from a race into a certainty: the bystanders hit a frozen loop or a full
    slot pool every time.

    Args:
        client: A connected Temporal client.
        bad_geo_inputs: The geo runs in the bad mode that freeze the loop or take the slots.
        healthy_geo_inputs: Healthy geo runs submitted as bystanders.
        receipt_inputs: Order-receipt runs submitted as bystanders.
    """
    baseline_free = await _read_free_activity_slots()
    target_free = max(0, baseline_free - len(bad_geo_inputs)) if baseline_free is not None else 0

    bad_handles = await _start_geo(client, bad_geo_inputs)

    if not await wait_for_free_activity_slots(target_free):
        print("warning: the bad geo activities did not take every slot in time; submitting bystanders anyway")

    healthy_handles = await _start_geo(client, healthy_geo_inputs)
    receipt_handles = await _start_receipts(client, receipt_inputs)

    # Bystanders fail first while the slots are held, so surface them before the long bad runs.
    await _report_results("geo", healthy_handles)
    await _report_results("receipt", receipt_handles)
    await _report_results("geo", bad_handles)


async def _run_all_concurrently(
    client: Client,
    geo_inputs: list[GeoEnrichmentInput],
    receipt_inputs: list[OrderReceiptInput],
) -> None:
    """Submit every geo and receipt run at once and print each result, for healthy runs."""
    geo_handles = await _start_geo(client, geo_inputs)
    receipt_handles = await _start_receipts(client, receipt_inputs)
    await _report_results("geo", geo_handles)
    await _report_results("receipt", receipt_handles)


async def main() -> None:
    """Parse the CLI flags, connect to the local server, and submit the fleet.

    A run that has bad geo workflows and any bystanders goes through the sequenced path, so the
    collateral failure is deterministic. Every other run submits concurrently.
    """
    args = build_parser().parse_args()
    bad_geo_inputs = bad_geo_inputs_from_args(args)
    healthy_geo_inputs = healthy_geo_inputs_from_args(args)
    receipt_inputs = receipt_inputs_from_args(args)

    client = await Client.connect(TEMPORAL_TARGET)

    if args.block_seconds > 0 and bad_geo_inputs and (healthy_geo_inputs or receipt_inputs):
        await _run_fleet_with_sequencing(client, bad_geo_inputs, healthy_geo_inputs, receipt_inputs)
    else:
        await _run_all_concurrently(client, [*bad_geo_inputs, *healthy_geo_inputs], receipt_inputs)


if __name__ == "__main__":
    asyncio.run(main())
    # WORKAROUND: temporalio's default Core runtime owns a process-wide Tokio thread pool
    # that Python only tears down during interpreter finalization, since neither Client
    # nor the default Runtime exposes a public close/shutdown call
    # (temporalio/sdk-python#300, still open on temporalio 1.33). That teardown
    # intermittently races a Tokio worker thread reacquiring the GIL while CPython is
    # finalizing: the worker thread parks forever and the process hangs on exit even
    # though every result already printed above. Once main() has returned, the run's
    # work is done, so skip Python's normal finalization, where the race lives, and exit
    # immediately instead of waiting for it.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
