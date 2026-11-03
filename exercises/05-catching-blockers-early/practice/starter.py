"""ABOUTME: The CLI that submits a fleet of geo-enrichment and bystander workflows to the worker.
ABOUTME: Exercise 05 (05-catching-blockers-early) copy; every geo run archives a large payload in get_location.

The starter submits a mixed fleet so the reader can watch one workflow type slow down another:

- ``--geo``: how many geo-enrichment runs to submit. Defaults to 0. Every one of them archives
  PAYLOAD_RECORDS audit records inside get_location, a few hundred milliseconds of work. Where that
  work runs decides whether it holds the worker's event loop. Nothing times out and every run
  completes.
- ``--receipts``: how many order-receipt runs to submit alongside. Defaults to 0.
- ``--rollups``: how many sales-rollup runs to submit alongside. Defaults to 0. A rollup holds an
  activity slot for five seconds, so leave it out when the point is the receipts' delay.

The receipts are instant in a healthy fleet, so any delay they show comes from the geo run. To make
the delay reproducible on every run, they go in only after the server reports the first geo run's
get_location as STARTED (polled through describe()) plus a short guard, which lands inside the
archiving. If the loop is held, their first workflow task is dispatched into that stall and
cannot finish until it ends. A fleet with no geo runs or no receipts submits everything at once.

Nothing here is labeled a victim; the reader finds the cause from the tooling, not from a name.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import traceback
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

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

GATE_ACTIVITY: str = get_location.__name__
"""The geo run's blocking activity, by the name the SDK registers and describe() reports."""

GATE_POLL_TIMEOUT_SECONDS: float = 20.0
"""How long the starter polls describe() for GATE_ACTIVITY to report STARTED before warning."""

GATE_POLL_INTERVAL_SECONDS: float = 0.02
"""Pause between describe() polls, short because the stall is only a few hundred milliseconds long.

A coarse interval (the other exercises poll every 0.25 seconds) could notice STARTED only after the
stall is over. At 20 ms the poll adds at most one interval plus a describe() round trip."""

GATE_GUARD_SECONDS: float = 0.025
"""Margin after the STARTED signal before the receipts, sized together with the stall.

The audit-trail archiving runs first in get_location, so it begins within a few
milliseconds of STARTED and lasts roughly 350 ms (PAYLOAD_RECORDS records on the capture machine).
Noticing STARTED costs up to one poll interval, the guard adds 25 ms, and starting a receipt is one
round trip to the server. The first receipt workflow task is therefore dispatched well inside the
archiving, with most of it still to run. A guard of a second, as in the other exercises, would let the
stall finish before the receipts were submitted and hide the delay."""

GATE_FALLBACK_DELAY_SECONDS: float = 0.1
"""Blind pause before the receipts when describe() does not answer; roughly the stall's first third."""

_GATE_NOT_CONFIRMED_CONSEQUENCE = "the receipts may be submitted after the stall and complete on time"
"""What an unconfirmed gate means for the run, appended to the gate's timeout warnings."""

Scenario = Literal["stall", "concurrent"]
"""The submission order a run uses: the stall ordering, or everything at once."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the starter CLI.

    Returns:
        An ArgumentParser defining --geo, --receipts, and --rollups with the demo's defaults.
    """
    parser = argparse.ArgumentParser(
        prog="temporal-async-debug",
        description="Submit a fleet of geo-enrichment and bystander workflows to the demo worker.",
    )
    parser.add_argument(
        "--geo",
        type=int,
        default=0,
        help="How many geo-enrichment runs to submit; each archives the large payload.",
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


def geo_inputs_from_args(args: argparse.Namespace) -> list[GeoEnrichmentInput]:
    """Build one GeoEnrichmentInput per requested geo run, each with the default payload size.

    Args:
        args: Parsed CLI arguments carrying the geo count.

    Returns:
        A list of ``args.geo`` GeoEnrichmentInput values.
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
        geo: Geo runs, each archiving the large payload inside get_location.
        receipts: Order-receipt runs, instant and no network.
        rollups: Sales-rollup runs, a few seconds of cooperative work.
    """

    geo: list[GeoEnrichmentInput]
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
        geo=geo_inputs_from_args(args),
        receipts=receipt_inputs_from_args(args),
        rollups=rollup_inputs_from_args(args),
    )


def select_scenario(fleet: Fleet) -> Scenario:
    """Pick the submission order for a fleet.

    Ordering only matters when there is a geo run to stall the worker and receipts for it to delay.

    Args:
        fleet: The runs to submit.

    Returns:
        "stall" when the receipts need to land inside the geo run's stall, or "concurrent" when
        nothing needs sequencing.
    """
    if not fleet.geo or not fleet.receipts:
        return "concurrent"
    return "stall"


async def wait_for_activity_started[WorkflowT, ResultT](
    handle: WorkflowHandle[WorkflowT, ResultT],
    activity_type: str,
    timeout_seconds: float,
) -> bool:
    """Poll describe() until the server reports the named activity of the workflow as STARTED.

    The server marks an activity STARTED when a worker's poll returns its task. describe() is a
    client-to-server call on the starter's own event loop, so a held worker loop cannot stall it.
    The poll is bounded by a fixed number of attempts, timeout_seconds divided by
    GATE_POLL_INTERVAL_SECONDS, so slow describe() round trips stretch it slightly past the timeout.

    Args:
        handle: The workflow whose pending activities to watch, for example the first geo run.
        activity_type: The registered activity name to wait for, for example GATE_ACTIVITY.
            Any other activity reporting STARTED does not count.
        timeout_seconds: How long to keep polling, for example GATE_POLL_TIMEOUT_SECONDS.

    Returns:
        True once that activity reports STARTED, False if it did not within the poll budget.

    Raises:
        RPCError: If describe() fails, for example when the server is unreachable.
    """
    for _ in range(round(timeout_seconds / GATE_POLL_INTERVAL_SECONDS)):
        description = await handle.describe()
        # The proto carries the state as a raw enum int; PendingActivityState is the SDK's IntEnum mirror.
        if any(
            pending.activity_type.name == activity_type and int(pending.state) == PendingActivityState.STARTED
            for pending in description.raw_description.pending_activities
        ):
            return True
        await asyncio.sleep(GATE_POLL_INTERVAL_SECONDS)
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


async def _submit_stall_scenario(client: Client, fleet: Fleet) -> None:
    """Submit the geo runs, wait for the archiving to begin, then submit the receipts inside it.

    The receipts are instant in a healthy fleet, so how long they take is the whole signal. They
    are submitted only after the server reports the first geo run's get_location,
    GATE_ACTIVITY, as STARTED (polled through describe()) plus a GATE_GUARD_SECONDS
    margin. The archiving is the first thing get_location does, so that lands inside it:
    when the loop is held, the receipts' first workflow task is dispatched into the stall and
    finishes only when it ends. If describe() fails or never reports the activity, the starter
    warns and pauses briefly instead.

    Args:
        client: A connected Temporal client.
        fleet: The runs to submit; fleet.geo holds the runs that archive the payload.
    """
    rollup_handles = await _start_rollups(client, fleet.rollups)
    geo_handles = await _start_geo(client, fleet.geo)

    # describe() goes from this process straight to the server, never through the worker, so the
    # held worker loop cannot block this poll.
    try:
        if not await wait_for_activity_started(geo_handles[0], GATE_ACTIVITY, GATE_POLL_TIMEOUT_SECONDS):
            print(
                f"warning: {GATE_ACTIVITY} never reported STARTED within {GATE_POLL_TIMEOUT_SECONDS}s; "
                f"{_GATE_NOT_CONFIRMED_CONSEQUENCE}"
            )
        await asyncio.sleep(GATE_GUARD_SECONDS)
    except RPCError as describe_error:
        print(
            f"warning: describe() failed ({describe_error}); pausing {GATE_FALLBACK_DELAY_SECONDS}s blind; "
            f"{_GATE_NOT_CONFIRMED_CONSEQUENCE}"
        )
        await asyncio.sleep(GATE_FALLBACK_DELAY_SECONDS)

    receipt_handles = await _start_receipts(client, fleet.receipts)

    await _report_results("receipt", receipt_handles)
    await _report_results("geo", geo_handles)
    await _report_results("rollup", rollup_handles)


async def _run_all_concurrently(client: Client, fleet: Fleet) -> None:
    """Submit every workflow run at once and print each result."""
    geo_handles = await _start_geo(client, fleet.geo)
    receipt_handles = await _start_receipts(client, fleet.receipts)
    rollup_handles = await _start_rollups(client, fleet.rollups)
    await _report_results("geo", geo_handles)
    await _report_results("receipt", receipt_handles)
    await _report_results("rollup", rollup_handles)


async def main() -> None:
    """Parse the CLI flags, connect to the local server, and submit the fleet.

    select_scenario picks the gated ordering when there are receipts for the geo run's stall to
    delay (see the module docstring), so the delay is reproducible rather than a race. Every other
    run submits concurrently.
    """
    args = build_parser().parse_args()
    client = await Client.connect(TEMPORAL_TARGET)

    fleet = fleet_from_args(args)
    match select_scenario(fleet):
        case "stall":
            await _submit_stall_scenario(client, fleet)
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
