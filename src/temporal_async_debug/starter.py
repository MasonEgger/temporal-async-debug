"""ABOUTME: The CLI that submits a fleet of geo-enrichment and bystander workflows to the worker.
ABOUTME: Parsing and input construction are pure functions so they unit-test without a server.

The starter submits a mixed fleet so the reader can watch one workflow type take down another:

- ``--mode``: how a bad geo-enrichment run delays, one of shared.VALID_MODES. Defaults to "block".
- ``--block-seconds``: seconds of delay each bad geo activity applies. Defaults to 0.0.
- ``--bad``: how many geo-enrichment runs to submit in the bad mode. Defaults to 0.
- ``--geo``: how many healthy geo-enrichment runs to submit alongside. Defaults to 0.
- ``--receipts``: how many order-receipt runs to submit alongside. Defaults to 0.
- ``--rollups``: how many sales-rollup runs to submit alongside. Defaults to 0.
- ``--quotes``: how many price-quote runs to submit alongside. Defaults to 0.

The two mode families need opposite submission orders to make their timeouts fire every run
instead of racing (spec's Starting context, live-verified):

- Freeze modes ("block", "cpu") stop the worker's event loop, which stops it from scheduling new
  activity tasks. Only a bystander already in-flight or queued before the freeze lands trips a
  timeout, so the starter submits the short-work bystanders (rollups, healthy geo) first, waits for
  at least one activity slot to be occupied, and only then submits the freezing bad geo run. The
  instant bystanders (receipts, quotes) go in only after the server reports the bad activity as
  STARTED (polled through describe()) and a short guard has passed, so their first workflow task
  cannot run until the loop thaws, and they stall and complete late. Without that gate, a
  bystander whose activity is scheduled while both slots are held but before the lock lands fails
  ScheduleToStart instead.
- Saturation modes ("slow", "slow_heartbeat", "stuck_no_heartbeat") hold activity slots without
  freezing the loop, so the starter submits the bad geo runs first, waits for the activity slot
  gauge to show they hold their slots, and only then submits every bystander, which starve for a
  slot instead.

Nothing here is labeled a victim; the reader finds the cause from the tooling, not from a name.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import traceback
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import httpx
from temporalio.client import Client, PendingActivityState, WorkflowFailureError, WorkflowHandle
from temporalio.service import RPCError

from temporal_async_debug.quote import PriceQuoteWorkflow
from temporal_async_debug.receipt import OrderReceiptWorkflow
from temporal_async_debug.rollup import SalesRollupWorkflow
from temporal_async_debug.shared import (
    TASK_QUEUE,
    VALID_MODES,
    GeoEnrichmentInput,
    OrderReceiptInput,
    PriceQuoteInput,
    SalesRollupInput,
)
from temporal_async_debug.workflow import GeoEnrichmentWorkflow

if TYPE_CHECKING:
    from temporal_async_debug.shared import (
        GeoEnrichmentOutput,
        OrderReceiptOutput,
        PriceQuoteOutput,
        SalesRollupOutput,
    )

FREEZE_MODES: frozenset[str] = frozenset({"block", "cpu"})
"""Modes that freeze the event loop; short-work bystanders must be in flight before the bad run lands."""

SATURATION_MODES: frozenset[str] = frozenset({"slow", "slow_heartbeat", "stuck_no_heartbeat"})
"""Modes that hold activity slots without freezing the loop; the bad run must fill slots first."""

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

LOCK_POLL_TIMEOUT_SECONDS: float = 20.0
"""How long to poll describe() for the bad activity to report STARTED before giving up with a warning."""

LOCK_POLL_INTERVAL_SECONDS: float = 0.25
"""Pause between describe() polls while waiting for the bad activity to report STARTED."""

FREEZE_LOCK_GUARD_SECONDS: float = 1.0
"""Margin after the lock signal before the instant bystanders, so the freezing call has time to run."""

FREEZE_FALLBACK_DELAY_SECONDS: float = 3.0
"""Blind pause before the instant bystanders when neither describe() nor the metrics endpoint answers."""

_LOCK_NOT_CONFIRMED_CONSEQUENCE = (
    "the loop may not be locked, so the receipts and quotes may complete on time instead of stalling"
)
"""What an unconfirmed lock means for the run, appended to the gate's timeout warnings."""

Scenario = Literal["freeze", "saturation", "concurrent"]
"""The submission order a run uses: freeze-family, saturation-family, or everything at once."""

_ACTIVITY_SLOTS_PATTERN = re.compile(
    r'temporal_worker_task_slots_available\{[^}]*worker_type="ActivityWorker"[^}]*\}\s+([0-9.]+)'
)
"""Matches the ActivityWorker free-slot gauge line, avoiding the LocalActivityWorker line."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the starter CLI.

    Returns:
        An ArgumentParser defining --mode, --block-seconds, --bad, --geo, --receipts,
        --rollups, and --quotes with the demo's healthy defaults.
    """
    parser = argparse.ArgumentParser(
        prog="temporal-async-debug",
        description="Submit a fleet of geo-enrichment and bystander workflows to the demo worker.",
    )
    parser.add_argument(
        "--mode",
        choices=list(VALID_MODES),
        default="block",
        help="How a bad geo run misbehaves; see shared.VALID_MODES for the full catalog.",
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
    parser.add_argument(
        "--rollups",
        type=int,
        default=0,
        help="How many sales-rollup runs to submit alongside.",
    )
    parser.add_argument(
        "--quotes",
        type=int,
        default=0,
        help="How many price-quote runs to submit alongside.",
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


def rollup_inputs_from_args(args: argparse.Namespace) -> list[SalesRollupInput]:
    """Build one SalesRollupInput per requested rollup run, each with a distinct period.

    Args:
        args: Parsed CLI arguments carrying the rollups count.

    Returns:
        A list of ``args.rollups`` SalesRollupInput values with distinct periods.
    """
    return [SalesRollupInput(period=f"2026-{run_index + 1:02d}") for run_index in range(args.rollups)]


def quote_inputs_from_args(args: argparse.Namespace) -> list[PriceQuoteInput]:
    """Build one PriceQuoteInput per requested quote run, each with a distinct sku.

    Args:
        args: Parsed CLI arguments carrying the quotes count.

    Returns:
        A list of ``args.quotes`` PriceQuoteInput values with distinct skus.
    """
    return [PriceQuoteInput(sku=f"SKU-{run_index}") for run_index in range(args.quotes)]


@dataclass(frozen=True)
class Fleet:
    """Every workflow input one starter run submits, grouped by kind.

    Attributes:
        bad_geo: Geo runs in the misbehaving mode.
        healthy_geo: Geo runs with no delay.
        receipts: Order-receipt runs, instant and no network.
        rollups: Sales-rollup runs, a few seconds of cooperative work.
        quotes: Price-quote runs, the schedule-to-start sample.
    """

    bad_geo: list[GeoEnrichmentInput]
    healthy_geo: list[GeoEnrichmentInput]
    receipts: list[OrderReceiptInput]
    rollups: list[SalesRollupInput]
    quotes: list[PriceQuoteInput]


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
        quotes=quote_inputs_from_args(args),
    )


def select_scenario(mode: str, block_seconds: float, fleet: Fleet) -> Scenario:
    """Pick the submission order for a fleet.

    Ordering only matters when there are bad runs that actually misbehave and at least one
    bystander of any kind for them to hurt; every bystander kind joins either family's scenario.

    Args:
        mode: The bad runs' mode, one of shared.VALID_MODES.
        block_seconds: The bad runs' delay; zero means they are healthy.
        fleet: The runs to submit.

    Returns:
        "freeze" or "saturation" for the mode's family, or "concurrent" when nothing needs
        sequencing.
    """
    has_bystanders = bool(fleet.healthy_geo or fleet.receipts or fleet.rollups or fleet.quotes)
    if block_seconds <= 0 or not fleet.bad_geo or not has_bystanders:
        return "concurrent"
    if mode in FREEZE_MODES:
        return "freeze"
    if mode in SATURATION_MODES:
        return "saturation"
    return "concurrent"


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


async def wait_for_activity_started[WorkflowT, ResultT](handle: WorkflowHandle[WorkflowT, ResultT]) -> bool:
    """Poll describe() until the server reports one of the workflow's activities as STARTED.

    The server marks an activity STARTED when a worker's poll returns its task. describe() is a
    client-to-server call on the starter's own event loop, so a frozen worker loop cannot stall it.
    The poll is bounded by a fixed number of attempts, LOCK_POLL_TIMEOUT_SECONDS divided by
    LOCK_POLL_INTERVAL_SECONDS, so slow describe() round trips stretch it slightly past the timeout.

    Args:
        handle: The workflow whose pending activities to watch, for example the first bad geo run.

    Returns:
        True once a pending activity reports STARTED, False if none did within the poll budget.

    Raises:
        RPCError: If describe() fails, for example when the server is unreachable.
    """
    for _ in range(round(LOCK_POLL_TIMEOUT_SECONDS / LOCK_POLL_INTERVAL_SECONDS)):
        description = await handle.describe()
        # The proto carries the state as a raw enum int; PendingActivityState is the SDK's IntEnum mirror.
        if any(
            int(pending.state) == PendingActivityState.STARTED
            for pending in description.raw_description.pending_activities
        ):
            return True
        await asyncio.sleep(LOCK_POLL_INTERVAL_SECONDS)
    return False


async def _report_results[WorkflowT, ResultT](label: str, handles: list[WorkflowHandle[WorkflowT, ResultT]]) -> None:
    """Await each workflow handle and print its result, or its failure if it timed out.

    Args:
        label: A short word naming the batch, for example "geo", "receipt", "rollup", or "quote".
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


async def _start_quotes(
    client: Client,
    inputs: list[PriceQuoteInput],
) -> list[WorkflowHandle[PriceQuoteWorkflow, PriceQuoteOutput]]:
    """Start one PriceQuoteWorkflow per input and return the handles without awaiting them."""
    return [
        await client.start_workflow(
            PriceQuoteWorkflow.run,
            quote_input,
            id=f"quote-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        for quote_input in inputs
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
    """Submit the short-work bystanders, freeze the loop once one holds a slot, then pile on more.

    A frozen loop stops scheduling new activity tasks, so only a bystander already in-flight or
    queued before the freeze lands trips a timeout. Submitting the rollups and healthy geo runs
    first and confirming at least one activity slot is occupied before the bad geo run lands turns
    that into a certainty instead of a race.

    The receipts and quotes are instant, so they show the other half of the lesson: they are
    submitted only after the server reports the first bad geo run's activity as STARTED, polled
    through describe(), plus a FREEZE_LOCK_GUARD_SECONDS margin. STARTED means a worker's poll
    returned the task; in the freeze modes the freezing call is the first thing the activity body
    runs, so the lock normally lands within milliseconds of that report, and the guard covers the
    gap. Their first workflow task then cannot run until the loop thaws, so they stall and complete
    late. Submitted any earlier, a bystander whose activity is scheduled while both slots are held
    but before the lock lands fails ScheduleToStart instead; the gate exists to keep the run off
    that knife-edge. If describe() never reports STARTED in time, the starter warns and submits
    anyway after the guard.

    If describe() itself fails, the gate falls back to the slot gauge: it waits for the free count
    to drop by the bad activity's slot, and by one more when a rollup or healthy geo run is holding
    a slot too. The metrics endpoint is served by the worker's Rust core, so the gauge stays
    readable during the freeze. When metrics are also unreachable, the last resort is a blind
    FREEZE_FALLBACK_DELAY_SECONDS pause.

    Args:
        client: A connected Temporal client.
        fleet: The runs to submit; fleet.bad_geo holds the runs in a freeze mode ("block" or "cpu").
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

    bad_handles = await _start_geo(client, fleet.bad_geo)

    if fleet.receipts or fleet.quotes:
        # describe() goes from this process straight to the server, never through the worker, so the
        # frozen worker loop cannot block this poll.
        try:
            if not await wait_for_activity_started(bad_handles[0]):
                print(
                    f"warning: the bad activity never reported STARTED within {LOCK_POLL_TIMEOUT_SECONDS}s; "
                    f"{_LOCK_NOT_CONFIRMED_CONSEQUENCE}"
                )
            await asyncio.sleep(FREEZE_LOCK_GUARD_SECONDS)
        except RPCError as describe_error:
            if baseline_free is None:
                print(
                    f"warning: describe() failed ({describe_error}) and the metrics endpoint is unreachable; "
                    f"pausing {FREEZE_FALLBACK_DELAY_SECONDS}s blind; {_LOCK_NOT_CONFIRMED_CONSEQUENCE}"
                )
                await asyncio.sleep(FREEZE_FALLBACK_DELAY_SECONDS)
            else:
                print(f"warning: describe() failed ({describe_error}); falling back to the activity slot gauge")
                # The bad activity takes one slot, and a rollup or healthy geo run may hold another.
                lock_target = max(0, baseline_free - (1 if has_early_bystanders else 0) - 1)
                if not await wait_for_free_activity_slots(lock_target):
                    print(
                        f"warning: the slot gauge never fell to {lock_target} free; {_LOCK_NOT_CONFIRMED_CONSEQUENCE}"
                    )
                await asyncio.sleep(FREEZE_LOCK_GUARD_SECONDS)

    receipt_handles = await _start_receipts(client, fleet.receipts)
    quote_handles = await _start_quotes(client, fleet.quotes)

    # The in-flight rollup fails first, so report it before the healthy geo runs that survive the
    # freeze; the receipts and quotes complete once the freeze clears, and the bad run ends last.
    await _report_results("rollup", rollup_handles)
    await _report_results("geo", healthy_handles)
    await _report_results("receipt", receipt_handles)
    await _report_results("quote", quote_handles)
    await _report_results("geo", bad_handles)


async def _submit_saturation_scenario(client: Client, fleet: Fleet) -> None:
    """Submit the bad geo runs first, wait until they hold their slots, then submit bystanders.

    Saturation modes hold activity slots without freezing the loop, so starting the bad runs
    first and confirming they have taken their slots before the bystanders arrive is what turns
    the starvation into a certainty: the bystanders starve for a slot every time. The wait target
    is the baseline free count minus one slot per bad run, floored at zero, so a single bad run on
    a two-slot worker waits for one free slot instead of running out the poll timeout.

    Args:
        client: A connected Temporal client.
        fleet: The runs to submit; fleet.bad_geo holds the runs in a saturation mode ("slow",
            "slow_heartbeat", or "stuck_no_heartbeat") that fill the worker's activity slots.
    """
    baseline_free = await _read_baseline_free_slots()

    bad_handles = await _start_geo(client, fleet.bad_geo)

    if baseline_free is not None and not await wait_for_free_activity_slots(max(0, baseline_free - len(fleet.bad_geo))):
        print("warning: the bad geo activities did not take their slots in time; submitting bystanders anyway")

    receipt_handles = await _start_receipts(client, fleet.receipts)
    rollup_handles = await _start_rollups(client, fleet.rollups)
    quote_handles = await _start_quotes(client, fleet.quotes)
    healthy_handles = await _start_geo(client, fleet.healthy_geo)

    # Bystanders fail first while the slots are held, so surface them before the long bad runs.
    await _report_results("receipt", receipt_handles)
    await _report_results("rollup", rollup_handles)
    await _report_results("quote", quote_handles)
    await _report_results("geo", healthy_handles)
    await _report_results("geo", bad_handles)


async def _run_all_concurrently(client: Client, fleet: Fleet) -> None:
    """Submit every workflow run at once and print each result, for healthy runs."""
    geo_handles = await _start_geo(client, [*fleet.bad_geo, *fleet.healthy_geo])
    receipt_handles = await _start_receipts(client, fleet.receipts)
    rollup_handles = await _start_rollups(client, fleet.rollups)
    quote_handles = await _start_quotes(client, fleet.quotes)
    await _report_results("geo", geo_handles)
    await _report_results("receipt", receipt_handles)
    await _report_results("rollup", rollup_handles)
    await _report_results("quote", quote_handles)


async def main() -> None:
    """Parse the CLI flags, connect to the local server, and submit the fleet.

    select_scenario picks the submission order that matches the bad runs' mode family, freeze or
    saturation (see the module docstring), so the collateral failure is deterministic rather than
    a race. Every other run submits concurrently.
    """
    args = build_parser().parse_args()
    fleet = fleet_from_args(args)

    client = await Client.connect(TEMPORAL_TARGET)

    match select_scenario(args.mode, args.block_seconds, fleet):
        case "freeze":
            await _submit_freeze_scenario(client, fleet)
        case "saturation":
            await _submit_saturation_scenario(client, fleet)
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
