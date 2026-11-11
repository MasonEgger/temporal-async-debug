"""ABOUTME: The flood starter: steady receipt traffic on the one task queue, with one bad geo run in the middle.
ABOUTME: Exercise 06 (06-finding-the-frozen-worker) copy; the bad run's location lookup waits on a held cache lock.

The flood submits ``--rate`` order receipts per second (default 10), each at its own due time, never
in a burst. After ``--lead`` seconds (default 10) it submits ``--rollups`` sales rollups (default 1),
waits 1 second, and submits ``--bad`` geo runs (default 1) pointed at a location cache whose lock the
starter holds for ``--block-seconds`` (default 30), counted from the moment the bad runs are submitted.
It then waits until the server reports the first bad run's get_location as STARTED, polled through
describe() for at most 20 seconds. That moment is the confirmed freeze, the zero point of the
timeline; if the gate times out, the starter says so in one line and times the timeline from the bad
run's submit instead. The receipts keep coming until ``--tail`` seconds (default 10) after the bad
runs return.

``--bad 0`` is the healthy flood: the same stream for the same length, lead plus block plus tail, with
the rollups after the lead and no lock held. Its timeline's zero point is the end of the lead.

A failed receipt never stops the flood. At the end the starter prints one closing summary and no line
per workflow: the receipts submitted, how many failed, the first failure's message, the outcome of each
rollup and each bad run, and the timeline in 5-second buckets by submit time. If the producer woke more
than one receipt's spacing late at any point, a one-line note with the total slip precedes the summary.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
import tempfile
import traceback
import uuid
from itertools import count
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

from activities import get_location
from db_lock import hold_cache_lock
from flood import ReceiptRecord, due_time, flood_due_times, format_summary, planned_duration, summarize
from receipt import OrderReceiptWorkflow
from rollup import SalesRollupWorkflow
from shared import TASK_QUEUE, GeoEnrichmentInput, OrderReceiptInput, SalesRollupInput
from temporalio.client import Client, PendingActivityState, WorkflowFailureError, WorkflowHandle
from workflow import GeoEnrichmentWorkflow

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from db_lock import CacheLock

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the starter submits to."""

FREEZE_GATE_ACTIVITY: str = get_location.__name__
"""The bad geo run's lookup activity, by the name the SDK registers and describe() reports."""

GATE_TIMEOUT_SECONDS: float = 20.0
"""How long the starter polls describe() for FREEZE_GATE_ACTIVITY to report STARTED."""

GATE_POLL_INTERVAL_SECONDS: float = 0.25
"""Pause between describe() polls while waiting for FREEZE_GATE_ACTIVITY to report STARTED."""

ROLLUP_HEAD_START_SECONDS: float = 1.0
"""Pause between submitting the rollups and submitting the bad runs."""


def _positive_float(text: str) -> float:
    """Parse a flag value that must be a number greater than 0."""
    value = float(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"invalid value {text!r}: must be greater than 0")
    return value


def _non_negative_float(text: str) -> float:
    """Parse a flag value that must be a number of seconds, 0 or more."""
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"invalid value {text!r}: must be 0 or more")
    return value


def _non_negative_int(text: str) -> int:
    """Parse a flag value that must be a whole count, 0 or more."""
    value = int(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"invalid value {text!r}: must be 0 or more")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the flood starter.

    Returns:
        An ArgumentParser defining --rate, --lead, --block-seconds, --tail, --rollups, and --bad,
        with the default flood: 10 receipts per second for 10 + 30 + 10 seconds, one rollup, one bad run.
    """
    parser = argparse.ArgumentParser(
        prog="temporal-async-debug",
        description="Flood the task queue with receipts, with one bad geo run in the middle, and summarize.",
    )
    parser.add_argument(
        "--rate",
        type=_positive_float,
        default=10.0,
        help="Receipts submitted per second, each at its own due time.",
    )
    parser.add_argument(
        "--lead",
        type=_non_negative_float,
        default=10.0,
        help="Seconds of receipts before the rollups and the bad runs are submitted.",
    )
    parser.add_argument(
        "--block-seconds",
        type=_non_negative_float,
        default=30.0,
        help="Seconds the cache lock is held, counted from the bad runs' submit.",
    )
    parser.add_argument(
        "--tail",
        type=_non_negative_float,
        default=10.0,
        help="Seconds of receipts after the bad runs return.",
    )
    parser.add_argument(
        "--rollups",
        type=_non_negative_int,
        default=1,
        help="How many sales rollups to submit after the lead.",
    )
    parser.add_argument(
        "--bad",
        type=_non_negative_int,
        default=1,
        help="How many geo runs to point at the locked cache; 0 runs the healthy flood with no lock.",
    )
    return parser


async def wait_for_activity_started[WorkflowT, ResultT](
    handle: WorkflowHandle[WorkflowT, ResultT],
    activity_type: str,
    timeout_seconds: float,
) -> bool:
    """Poll describe() until the server reports the named activity of the workflow as STARTED.

    The server marks an activity STARTED when a worker's poll returns its task. describe() is a
    client-to-server call on the starter's own event loop, so a frozen worker loop cannot stall it.
    The poll is bounded by a fixed number of attempts, timeout_seconds divided by
    GATE_POLL_INTERVAL_SECONDS, so slow describe() round trips stretch it slightly past the timeout.

    Args:
        handle: The workflow whose pending activities to watch, for example the first bad geo run.
        activity_type: The registered activity name to wait for, for example FREEZE_GATE_ACTIVITY.
            Any other activity reporting STARTED does not count.
        timeout_seconds: How long to keep polling, for example GATE_TIMEOUT_SECONDS.

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


def describe_failure(failure: WorkflowFailureError) -> str:
    """Join a workflow failure's cause chain into one line.

    Args:
        failure: The failure a workflow handle's result() raised.

    Returns:
        Each cause's message, outermost first, joined by "caused by", for example
        "Activity task failed caused by activity ScheduleToClose timeout caused by activity StartToClose timeout".
    """
    messages = []
    cause: BaseException | None = failure.cause
    while cause is not None:
        messages.append(str(cause))
        cause = cause.__cause__
    return " caused by ".join(messages)


async def _outcome[WorkflowT, ResultT](handle: WorkflowHandle[WorkflowT, ResultT]) -> str:
    """Wait for a workflow to close and return "completed" or "FAILED: <cause chain>"."""
    try:
        await handle.result()
    except WorkflowFailureError as failure:
        return f"FAILED: {describe_failure(failure)}"
    return "completed"


async def _run_receipt(client: Client, order_number: int, flood_start: float) -> ReceiptRecord:
    """Submit one order receipt, wait for it to close, and record when it went in and how long it took."""
    submitted_at = monotonic()
    handle = await client.start_workflow(
        OrderReceiptWorkflow.run,
        OrderReceiptInput(order_id=f"order-{order_number}", item_count=3, unit_price_cents=1999),
        id=f"receipt-{uuid.uuid4()}",
        task_queue=TASK_QUEUE,
    )
    failure_message = None
    try:
        await handle.result()
    except WorkflowFailureError as failure:
        failure_message = describe_failure(failure)
    return ReceiptRecord(
        submit_offset=submitted_at - flood_start,
        latency_seconds=monotonic() - submitted_at,
        failed=failure_message is not None,
        failure_message=failure_message,
    )


async def _produce(
    client: Client,
    rate: float,
    due_times: Iterable[float],
    flood_start: float,
    stop: asyncio.Event,
) -> tuple[list[ReceiptRecord], float]:
    """Submit one receipt at each due time until the plan runs out or stop is set.

    Each receipt runs in its own task, so a slow or failed one never holds up the next submit. If
    the producer wakes more than one receipt's spacing (1 / rate) late, it does not fire the missed
    receipts at once to catch up: it shifts every later due time by the delay, so the stream keeps
    its spacing and only ends later. The total shift is returned so the caller can report it.

    Args:
        client: A connected Temporal client.
        rate: Receipts per second.
        due_times: When each receipt is due, in seconds from flood_start.
        flood_start: The flood's start, on the monotonic clock.
        stop: Set by the caller to end an open-ended plan.

    Returns:
        One record per submitted receipt, and the seconds the plan slipped by.
    """
    spacing = 1 / rate
    slip = 0.0
    tasks = []
    async with asyncio.TaskGroup() as group:
        for order_number, due in enumerate(due_times):
            submit_at = flood_start + due + slip
            await asyncio.sleep(max(0.0, submit_at - monotonic()))
            if stop.is_set():
                break
            # A late wake within one spacing is timer jitter; anything later shifts the rest of the plan.
            lateness = monotonic() - submit_at
            if lateness > spacing:
                slip += lateness
            tasks.append(group.create_task(_run_receipt(client, order_number, flood_start)))
    return [task.result() for task in tasks], slip


async def run_flood(client: Client, args: argparse.Namespace) -> None:
    """Run one flood from the parsed flags and print its closing summary.

    With ``--bad`` at 1 or more, the flood holds the cache lock in a temporary directory that is
    removed when the flood ends. With ``--bad 0`` it takes no lock and creates no directory.

    Args:
        client: A connected Temporal client.
        args: Parsed flags from build_parser.
    """
    with contextlib.ExitStack() as cleanup:
        # Prepare: the lock, only for a bad flood, and the receipt plan, open-ended for a bad flood.
        lock: CacheLock | None = None
        due_times: Iterable[float] = flood_due_times(
            args.rate, planned_duration(args.lead, args.block_seconds, args.tail)
        )
        if args.bad:
            directory = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix="flood-")))
            lock = cleanup.enter_context(hold_cache_lock(args.block_seconds, directory))
            due_times = (due_time(order_number, args.rate) for order_number in count())

        stop = asyncio.Event()
        flood_start = monotonic()
        zero_offset, zero_point = args.lead, "the end of the lead"
        bad_outcomes: list[tuple[str, str]] = []
        async with asyncio.TaskGroup() as group:
            producer = group.create_task(_produce(client, args.rate, due_times, flood_start, stop))

            # After the lead: the rollups, then for a bad flood the bad runs, the lock's arm, and the gate.
            await asyncio.sleep(max(0.0, flood_start + args.lead - monotonic()))
            rollup_handles = [
                await client.start_workflow(
                    SalesRollupWorkflow.run,
                    SalesRollupInput(period=f"2026-{rollup_number + 1:02d}"),
                    id=f"rollup-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )
                for rollup_number in range(args.rollups)
            ]
            if lock is not None:
                await asyncio.sleep(ROLLUP_HEAD_START_SECONDS)
                bad_input = GeoEnrichmentInput(location_cache_path=str(lock.database_path))
                bad_handles = [
                    await client.start_workflow(
                        GeoEnrichmentWorkflow.run,
                        bad_input,
                        id=f"geo-{uuid.uuid4()}",
                        task_queue=TASK_QUEUE,
                    )
                    for _ in range(args.bad)
                ]
                lock.arm()
                bad_submit_offset = monotonic() - flood_start
                if await wait_for_activity_started(bad_handles[0], FREEZE_GATE_ACTIVITY, GATE_TIMEOUT_SECONDS):
                    zero_offset, zero_point = monotonic() - flood_start, "the confirmed freeze"
                else:
                    print(
                        f"freeze not confirmed: {FREEZE_GATE_ACTIVITY} did not report STARTED within "
                        f"{GATE_TIMEOUT_SECONDS:g}s; the timeline is timed from the bad run's submit"
                    )
                    zero_offset, zero_point = bad_submit_offset, "the bad run's submit time"

                # The receipts run on until --tail seconds after the last bad run returns.
                bad_outcomes = [(f"geo {handle.id}", await _outcome(handle)) for handle in bad_handles]
                await asyncio.sleep(args.tail)
                stop.set()

            records, slip = await producer

        # Report: the slip, if any, then the closing summary.
        outcomes = [(f"rollup {handle.id}", await _outcome(handle)) for handle in rollup_handles] + bad_outcomes
        if slip > 0:
            print(f"note: the producer fell {slip:.2f}s behind its plan; later receipts kept their spacing")
        print("\n".join(format_summary(summarize(records, zero_offset), outcomes, zero_point)))


async def main(argv: Sequence[str] | None = None) -> None:
    """Parse the flags, connect to the local server, and run the flood.

    Args:
        argv: The flags to parse; None reads them from the command line.
    """
    args = build_parser().parse_args(argv)
    client = await Client.connect(TEMPORAL_TARGET)
    await run_flood(client, args)


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
        # temporalio's default Core runtime owns a process-wide Tokio thread pool that Python only
        # tears down during interpreter finalization, and neither Client nor the default Runtime
        # exposes a public close call (temporalio/sdk-python#300, open on temporalio 1.33). That
        # teardown can race a Tokio worker thread reacquiring the GIL while CPython finalizes, and
        # the process then hangs on exit after every line has printed. Once main() has returned the
        # flood is done, so skip Python's finalization and exit at once, on every exit path.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(exit_code)
