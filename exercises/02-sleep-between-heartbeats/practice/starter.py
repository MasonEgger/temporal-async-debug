"""ABOUTME: The CLI that submits a fleet of geo-enrichment and bystander workflows to the worker.
ABOUTME: Exercise 02 (02-sleep-between-heartbeats) copy; --bad runs poll a simulated slow job for the location.

The starter submits a mixed fleet so the reader can watch one workflow type take down another:

- ``--bad``: how many geo-enrichment runs to have poll the slow job. Defaults to 0.
- ``--geo``: how many healthy geo-enrichment runs to submit alongside. Defaults to 0.
- ``--receipts``: how many order-receipt runs to submit alongside. Defaults to 0.
- ``--rollups``: how many sales-rollup runs to submit alongside. Defaults to 0.

Healthy geo runs ask the real providers and finish in well under a second. A bad run's get_location
polls a simulated slow job that takes about 20 seconds, waiting 8 seconds between polls. Only a
bystander already in flight when the freeze begins trips a timeout, so the starter submits the rollups
first and waits for one of them to take an activity slot, then waits for the healthy geo runs to
finish, then submits the bad run. The receipts go in only after the server reports the bad run's
get_location as STARTED (polled through describe()) plus a short guard, so they stall behind the freeze
and complete when it ends. A fleet with no bad runs submits everything at once.

Nothing here is labeled a victim; the reader finds the cause from the tooling, not from a name.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import re
import sys
import traceback
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx
from activities import get_location
from receipt import OrderReceiptWorkflow
from rollup import SalesRollupWorkflow
from shared import (
    TASK_QUEUE,
    GeoEnrichmentInput,
    OrderReceiptInput,
    SalesRollupInput,
)
from temporalio.client import Client, PendingActivityState, WorkflowFailureError, WorkflowHandle
from temporalio.service import RPCError
from workflow import GeoEnrichmentWorkflow

if TYPE_CHECKING:
    from shared import (
        GeoEnrichmentOutput,
        OrderReceiptOutput,
        SalesRollupOutput,
    )

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the starter submits to."""

METRICS_URL: str = "http://127.0.0.1:9464/metrics"
"""Where the worker exports Prometheus metrics, including the activity slot gauge."""

METRICS_TIMEOUT_SECONDS: float = 3.0
"""Per-request timeout when scraping the metrics endpoint."""

SLOT_POLL_TIMEOUT_SECONDS: float = 20.0
"""How long to wait for an early bystander to take an activity slot before submitting the bad run anyway."""

SLOT_POLL_INTERVAL_SECONDS: float = 0.5
"""How often to re-scrape the slot gauge while waiting for the slots to fill."""

FREEZE_GATE_ACTIVITY: str = get_location.__name__
"""The bad geo run's slow activity, by the name the SDK registers and describe() reports."""

LOCK_POLL_TIMEOUT_SECONDS: float = 20.0
"""How long the starter polls describe() for FREEZE_GATE_ACTIVITY to report STARTED before warning."""

LOCK_POLL_INTERVAL_SECONDS: float = 0.25
"""Pause between describe() polls while waiting for FREEZE_GATE_ACTIVITY to report STARTED."""

FREEZE_LOCK_GUARD_SECONDS: float = 1.0
"""Margin after the lock signal before the instant bystanders, so the freezing call has time to run."""

FREEZE_FALLBACK_DELAY_SECONDS: float = 3.0
"""Blind pause before the instant bystanders when neither describe() nor the metrics endpoint answers."""

_LOCK_NOT_CONFIRMED_CONSEQUENCE = "the loop may not be locked, so the receipts may complete on time instead of stalling"
"""What an unconfirmed lock means for the run, appended to the gate's timeout warnings."""

Scenario = Literal["freeze", "concurrent"]
"""The submission order a run uses: the freeze ordering, or everything at once."""

_ACTIVITY_SLOTS_PATTERN = re.compile(
    r'temporal_worker_task_slots_available\{[^}]*worker_type="ActivityWorker"[^}]*\}\s+([0-9.]+)'
)
"""Matches the ActivityWorker free-slot gauge line, avoiding the LocalActivityWorker line."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the starter CLI.

    Returns:
        An ArgumentParser defining --bad, --geo, --receipts,
        and --rollups with the demo's healthy defaults.
    """
    parser = argparse.ArgumentParser(
        prog="temporal-async-debug",
        description="Submit a fleet of geo-enrichment and bystander workflows to the demo worker.",
    )
    parser.add_argument(
        "--bad",
        type=int,
        default=0,
        help="How many geo-enrichment runs to have poll the slow job.",
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
    parser.add_argument(
        "--rollups",
        type=int,
        default=0,
        help="How many sales-rollup runs to submit alongside.",
    )
    return parser


def bad_geo_inputs_from_args(args: argparse.Namespace) -> list[GeoEnrichmentInput]:
    """Build one GeoEnrichmentInput per bad geo run, each set to poll the slow job.

    Args:
        args: Parsed CLI arguments carrying the bad count.

    Returns:
        A list of ``args.bad`` GeoEnrichmentInput values with slow_job set.
    """
    return [GeoEnrichmentInput(slow_job=True) for _ in range(args.bad)]


def healthy_geo_inputs_from_args(args: argparse.Namespace) -> list[GeoEnrichmentInput]:
    """Build one healthy GeoEnrichmentInput per requested healthy geo run.

    Args:
        args: Parsed CLI arguments carrying the geo count.

    Returns:
        A list of ``args.geo`` GeoEnrichmentInput values that use the real providers.
    """
    return [GeoEnrichmentInput() for _ in range(args.geo)]


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


def rollup_inputs_from_args(args: argparse.Namespace) -> list[SalesRollupInput]:
    """Build one SalesRollupInput per requested rollup run, each with a distinct period.

    Args:
        args: Parsed CLI arguments carrying the rollups count.

    Returns:
        A list of ``args.rollups`` SalesRollupInput values with distinct periods.
    """
    return [SalesRollupInput(period=f"2026-{run_index + 1:02d}") for run_index in range(args.rollups)]


@dataclass(frozen=True)
class Fleet:
    """Every workflow input one starter run submits, grouped by kind.

    Attributes:
        bad_geo: Geo runs that poll the slow job.
        healthy_geo: Geo runs that use the real providers.
        receipts: Order-receipt runs, instant and no network.
        rollups: Sales-rollup runs, a few seconds of cooperative work.
    """

    bad_geo: list[GeoEnrichmentInput]
    healthy_geo: list[GeoEnrichmentInput]
    receipts: list[OrderReceiptInput]
    rollups: list[SalesRollupInput]


def fleet_from_args(args: argparse.Namespace) -> Fleet:
    """Build the full fleet from the parsed CLI flags.

    Args:
        args: Parsed CLI arguments from build_parser.

    Returns:
        A Fleet carrying one input per requested run of every kind.
    """
    return Fleet(
        bad_geo=bad_geo_inputs_from_args(args),
        healthy_geo=healthy_geo_inputs_from_args(args),
        receipts=receipt_inputs_from_args(args),
        rollups=rollup_inputs_from_args(args),
    )


def select_scenario(fleet: Fleet) -> Scenario:
    """Pick the submission order for a fleet.

    Ordering only matters when there are bad runs and at least one bystander of any kind
    for them to hurt; every bystander kind joins the freeze scenario.

    Args:
        fleet: The runs to submit.

    Returns:
        "freeze" when bad runs need the freeze ordering, or "concurrent" when nothing needs
        sequencing.
    """
    has_bystanders = bool(fleet.healthy_geo or fleet.receipts or fleet.rollups)
    if not fleet.bad_geo or not has_bystanders:
        return "concurrent"
    return "freeze"


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
        target_free: The free-slot count to wait for, for example 1 once an early bystander
            has taken a slot.

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


async def wait_for_activity_started[WorkflowT, ResultT](
    handle: WorkflowHandle[WorkflowT, ResultT],
    activity_type: str,
    timeout_seconds: float,
) -> bool:
    """Poll describe() until the server reports the named activity of the workflow as STARTED.

    The server marks an activity STARTED when a worker's poll returns its task. describe() is a
    client-to-server call on the starter's own event loop, so a frozen worker loop cannot stall it.
    The poll is bounded by a fixed number of attempts, timeout_seconds divided by
    LOCK_POLL_INTERVAL_SECONDS, so slow describe() round trips stretch it slightly past the timeout.

    Args:
        handle: The workflow whose pending activities to watch, for example the first bad geo run.
        activity_type: The registered activity name to wait for, for example FREEZE_GATE_ACTIVITY.
            Any other activity reporting STARTED does not count.
        timeout_seconds: How long to keep polling, for example LOCK_POLL_TIMEOUT_SECONDS.

    Returns:
        True once that activity reports STARTED, False if it did not within the poll budget.

    Raises:
        RPCError: If describe() fails, for example when the server is unreachable.
    """
    for _ in range(round(timeout_seconds / LOCK_POLL_INTERVAL_SECONDS)):
        description = await handle.describe()
        # The proto carries the state as a raw enum int; PendingActivityState is the SDK's IntEnum mirror.
        if any(
            pending.activity_type.name == activity_type and int(pending.state) == PendingActivityState.STARTED
            for pending in description.raw_description.pending_activities
        ):
            return True
        await asyncio.sleep(LOCK_POLL_INTERVAL_SECONDS)
    return False


async def _report_results[WorkflowT, ResultT](label: str, handles: list[WorkflowHandle[WorkflowT, ResultT]]) -> None:
    """Await each workflow handle and print its result, or its failure if it timed out.

    Args:
        label: A short word naming the batch, for example "geo", "receipt", or "rollup".
        handles: The started workflow handles to await in order.
    """
    for handle in handles:
        try:
            result = await handle.result()
        except WorkflowFailureError as failure:
            print(f"{label} {handle.id} FAILED: {failure.cause}")
        else:
            print(f"{label} {handle.id}: {result}")


async def _await_completion[WorkflowT, ResultT](handles: list[WorkflowHandle[WorkflowT, ResultT]]) -> None:
    """Wait for each workflow to close, succeeded or failed, without printing anything.

    A failure is not handled here: _report_results awaits the same handles later and prints it.

    Args:
        handles: The started workflow handles to wait on.
    """
    for handle in handles:
        with contextlib.suppress(WorkflowFailureError):
            await handle.result()


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


async def _start_rollups(
    client: Client,
    inputs: list[SalesRollupInput],
) -> list[WorkflowHandle[SalesRollupWorkflow, SalesRollupOutput]]:
    """Start one SalesRollupWorkflow per input and return the handles without awaiting them."""
    return [
        await client.start_workflow(
            SalesRollupWorkflow.run,
            rollup_input,
            id=f"rollup-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        for rollup_input in inputs
    ]


async def _read_baseline_free_slots() -> int | None:
    """Read the free activity slot count before submitting anything, warning if metrics are down.

    Returns:
        The free slot count, or None when the metrics endpoint did not answer, in which case the
        scenario submits without waiting on the slot gauge.
    """
    baseline_free = await _read_free_activity_slots()
    if baseline_free is None:
        print(f"warning: metrics endpoint unreachable at {METRICS_URL}; submitting without waiting for slots")
    return baseline_free


async def _submit_freeze_scenario(client: Client, fleet: Fleet) -> None:
    """Submit the rollups, wait for one to hold a slot, then the bad run, then the receipts.

    A frozen loop stops scheduling new activity tasks, so only a bystander already in flight
    before the wait begins trips a timeout. Submitting the rollups and healthy geo runs first and
    confirming one activity slot is occupied turns that into a certainty instead of a race. The
    healthy geo runs are then awaited, because they finish in well under a second.

    The receipts are instant, so they show the other half of the lesson. They are submitted only
    after the server reports the first bad run's get_location, FREEZE_GATE_ACTIVITY, as STARTED
    (polled through describe()) plus a FREEZE_LOCK_GUARD_SECONDS margin. Their first workflow task
    then cannot run until the blocking call returns, so they stall and complete late. If describe()
    fails or never reports the activity, the starter warns and pauses blind instead.

    Args:
        client: A connected Temporal client.
        fleet: The runs to submit; fleet.bad_geo holds the runs that poll the slow job.
    """
    baseline_free = await _read_baseline_free_slots()

    rollup_handles = await _start_rollups(client, fleet.rollups)
    healthy_handles = await _start_geo(client, fleet.healthy_geo)

    has_early_bystanders = bool(fleet.rollups or fleet.healthy_geo)
    if baseline_free == 0:
        print("warning: the worker already has no free activity slots (a prior run may still hold them); proceeding")
    if (
        baseline_free is not None
        and has_early_bystanders
        and not await wait_for_free_activity_slots(max(0, baseline_free - 1))
    ):
        print("warning: no bystander activity took a slot in time; submitting the freeze anyway")

    await _await_completion(healthy_handles)

    bad_handles = await _start_geo(client, fleet.bad_geo)

    if fleet.receipts:
        # describe() goes from this process straight to the server, never through the worker, so the
        # frozen worker loop cannot block this poll.
        try:
            if not await wait_for_activity_started(bad_handles[0], FREEZE_GATE_ACTIVITY, LOCK_POLL_TIMEOUT_SECONDS):
                print(
                    f"warning: {FREEZE_GATE_ACTIVITY} never reported STARTED within {LOCK_POLL_TIMEOUT_SECONDS}s; "
                    f"{_LOCK_NOT_CONFIRMED_CONSEQUENCE}"
                )
            await asyncio.sleep(FREEZE_LOCK_GUARD_SECONDS)
        except RPCError as describe_error:
            print(
                f"warning: describe() failed ({describe_error}); pausing {FREEZE_FALLBACK_DELAY_SECONDS}s blind; "
                f"{_LOCK_NOT_CONFIRMED_CONSEQUENCE}"
            )
            await asyncio.sleep(FREEZE_FALLBACK_DELAY_SECONDS)

    receipt_handles = await _start_receipts(client, fleet.receipts)

    # The in-flight rollup fails first, so report it before the healthy geo runs that finished before
    # the wait; the receipts complete once the blocking call returns, and the bad run ends last.
    await _report_results("rollup", rollup_handles)
    await _report_results("geo", healthy_handles)
    await _report_results("receipt", receipt_handles)
    await _report_results("geo", bad_handles)


async def _run_all_concurrently(client: Client, fleet: Fleet) -> None:
    """Submit every workflow run at once and print each result, for healthy runs."""
    geo_handles = await _start_geo(client, [*fleet.bad_geo, *fleet.healthy_geo])
    receipt_handles = await _start_receipts(client, fleet.receipts)
    rollup_handles = await _start_rollups(client, fleet.rollups)
    await _report_results("geo", geo_handles)
    await _report_results("receipt", receipt_handles)
    await _report_results("rollup", rollup_handles)


async def main() -> None:
    """Parse the CLI flags, connect to the local server, and submit the fleet.

    select_scenario picks the freeze ordering when bad runs have bystanders to hurt (see the module
    docstring), so the collateral failure is deterministic rather than a race. Every other run
    submits concurrently.
    """
    args = build_parser().parse_args()
    client = await Client.connect(TEMPORAL_TARGET)

    fleet = fleet_from_args(args)
    match select_scenario(fleet):
        case "freeze":
            await _submit_freeze_scenario(client, fleet)
        case "concurrent":
            await _run_all_concurrently(client, fleet)


def run_main() -> int:
    """Run main() to completion and turn every way it can end into a process exit code.

    Nothing escapes, so the os._exit teardown below always runs after it. Because os._exit skips
    Python's normal error report, a failure's traceback is printed here instead.

    Returns:
        0 on success, the requested status for SystemExit (argparse uses 2 for bad flags), 130 for
        Ctrl-C, and 1 for any other exception.
    """
    try:
        asyncio.run(main())
    except SystemExit as exit_request:
        if exit_request.code is None:
            return 0
        return exit_request.code if isinstance(exit_request.code, int) else 1
    except KeyboardInterrupt:
        return 130
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = run_main()
    finally:
        # WORKAROUND: temporalio's default Core runtime owns a process-wide Tokio thread pool
        # that Python only tears down during interpreter finalization, since neither Client
        # nor the default Runtime exposes a public close/shutdown call
        # (temporalio/sdk-python#300, still open on temporalio 1.33). That teardown
        # intermittently races a Tokio worker thread reacquiring the GIL while CPython is
        # finalizing: the worker thread parks forever and the process hangs on exit even
        # though every result already printed above. Once main() has returned, the run's
        # work is done, so skip Python's normal finalization, where the race lives, and exit
        # immediately instead of waiting for it. The finally clause makes this run on every
        # exit path, failures included.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
