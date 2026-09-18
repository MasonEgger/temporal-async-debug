"""ABOUTME: The CLI that submits GreetingWorkflow and VictimWorkflow runs to the demo worker.
ABOUTME: Parsing and input construction are pure functions so they unit-test without a server.

The starter parses a handful of flags and fans them out into concurrent workflow submissions:

- ``--name``: the name GreetingWorkflow greets. Defaults to "friend".
- ``--block-seconds``: seconds of delay each greeting activity applies. Defaults to 0.0, the
  healthy value, so a bare run does no delay at all.
- ``--mode``: how that delay is applied, "block" (freezes the worker's event loop, the bug the
  demo teaches) or "slow" (cooperative await that still holds an activity slot). Defaults to "block".
- ``--count``: how many GreetingWorkflow runs to submit. Two misbehaving runs fill the worker's
  two activity slots. Defaults to 1.
- ``--victims``: how many innocent VictimWorkflow runs to submit alongside. These are the workflows
  that starve while the greeting activities hog the loop or the slots. Defaults to 0.

Submitting several misbehaving greetings plus a few victims is what makes the failure legible: the
victims should be trivial and fast, so any timeout they suffer points straight at the mistuned worker.

When a run both delays the greetings and submits victims, the starter sequences the two on purpose so
the failure is never a race. It starts the greetings first, watches the worker's metrics endpoint until
the activity slot gauge shows the slots are taken, and only then submits the victims. The victims
therefore arrive with no slot to run in and fail on their schedule-to-start timeout every time.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import uuid

import httpx
from temporalio.client import Client, WorkflowFailureError, WorkflowHandle

from temporal_async_debug.shared import TASK_QUEUE, GreetingInput, VictimInput
from temporal_async_debug.victim import VictimWorkflow
from temporal_async_debug.workflow import GreetingWorkflow

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the starter submits to."""

METRICS_URL: str = "http://127.0.0.1:9464/metrics"
"""Where the worker exports Prometheus metrics, including the activity slot gauge."""

METRICS_TIMEOUT_SECONDS: float = 3.0
"""Per-request timeout when scraping the metrics endpoint."""

SLOT_POLL_TIMEOUT_SECONDS: float = 20.0
"""How long to wait for the greeting activities to take every slot before submitting victims anyway."""

SLOT_POLL_INTERVAL_SECONDS: float = 0.5
"""How often to re-scrape the slot gauge while waiting for the slots to fill."""

_ACTIVITY_SLOTS_PATTERN = re.compile(
    r'temporal_worker_task_slots_available\{[^}]*worker_type="ActivityWorker"[^}]*\}\s+([0-9.]+)'
)
"""Matches the ActivityWorker free-slot gauge line, avoiding the LocalActivityWorker line."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the starter CLI.

    Returns:
        An ArgumentParser defining --name, --block-seconds, --mode, --count, and --victims
        with the demo's healthy defaults.
    """
    parser = argparse.ArgumentParser(
        prog="temporal-async-debug",
        description="Submit misbehaving greeting workflows and innocent victim workflows to the demo worker.",
    )
    parser.add_argument("--name", default="friend", help="Name for GreetingWorkflow to greet.")
    parser.add_argument(
        "--block-seconds",
        type=float,
        default=0.0,
        help="Seconds of delay each greeting activity applies before its HTTP call.",
    )
    parser.add_argument(
        "--mode",
        choices=["block", "slow"],
        default="block",
        help="How the delay is applied: block freezes the event loop, slow awaits cooperatively.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="How many GreetingWorkflow runs to submit.",
    )
    parser.add_argument(
        "--victims",
        type=int,
        default=0,
        help="How many innocent VictimWorkflow runs to submit alongside the greetings.",
    )
    return parser


def greeting_inputs_from_args(args: argparse.Namespace) -> list[GreetingInput]:
    """Build one GreetingInput per requested greeting run.

    Args:
        args: Parsed CLI arguments carrying name, block_seconds, mode, and count.

    Returns:
        A list of ``args.count`` GreetingInput values, each carrying the same name, mode, and
        block_seconds, since every greeting run in a batch exercises the same failure mode.
    """
    return [GreetingInput(name=args.name, block_seconds=args.block_seconds, mode=args.mode) for _ in range(args.count)]


def victim_inputs_from_args(args: argparse.Namespace) -> list[VictimInput]:
    """Build one VictimInput per requested victim run, each with a distinct label.

    Args:
        args: Parsed CLI arguments carrying the victims count.

    Returns:
        A list of ``args.victims`` VictimInput values with distinct labels so each concurrent
        victim run is identifiable in the worker logs and the Temporal UI.
    """
    return [VictimInput(label=f"victim-{run_index}") for run_index in range(args.victims)]


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
        target_free: The free-slot count to wait for, for example 0 once the greetings hold
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
        label: A short word naming the batch, "greeting" or "victim", for the printed lines.
        handles: The started workflow handles to await in order.
    """
    for handle in handles:
        try:
            result = await handle.result()
        except WorkflowFailureError as failure:
            print(f"{label} {handle.id} FAILED: {failure.cause}")
        else:
            print(f"{label} {handle.id}: {result}")


async def _run_slot_exhaustion_demo(
    client: Client,
    greeting_inputs: list[GreetingInput],
    victim_inputs: list[VictimInput],
) -> None:
    """Fill the worker's slots with greetings, wait until they are taken, then submit the victims.

    Starting the greetings first and confirming the slots are gone before the victims arrive is what
    turns the failure from a race into a certainty: the victims have nowhere to run and time out.

    Args:
        client: A connected Temporal client.
        greeting_inputs: The misbehaving greeting runs that take the slots.
        victim_inputs: The innocent runs that should fail once the slots are gone.
    """
    baseline_free = await _read_free_activity_slots()
    target_free = max(0, baseline_free - len(greeting_inputs)) if baseline_free is not None else 0

    greeting_handles = [
        await client.start_workflow(
            GreetingWorkflow.run,
            greeting_input,
            id=f"greeting-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        for greeting_input in greeting_inputs
    ]

    if not await wait_for_free_activity_slots(target_free):
        print("warning: the greeting activities did not take every slot in time; submitting victims anyway")

    victim_handles = [
        await client.start_workflow(
            VictimWorkflow.run,
            victim_input,
            id=f"victim-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        for victim_input in victim_inputs
    ]

    # Victims fail fast on their schedule-to-start timeout, so surface them before the slow greetings.
    await _report_results("victim", victim_handles)
    await _report_results("greeting", greeting_handles)


async def _run_all_concurrently(
    client: Client,
    greeting_inputs: list[GreetingInput],
    victim_inputs: list[VictimInput],
) -> None:
    """Submit every greeting and victim at once and print each result, for healthy or single-batch runs."""
    results = await asyncio.gather(
        *(
            client.execute_workflow(
                GreetingWorkflow.run,
                greeting_input,
                id=f"greeting-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            for greeting_input in greeting_inputs
        ),
        *(
            client.execute_workflow(
                VictimWorkflow.run,
                victim_input,
                id=f"victim-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            for victim_input in victim_inputs
        ),
    )
    for result in results:
        print(result)


async def main() -> None:
    """Parse the CLI flags, connect to the local server, and submit the runs.

    A run that both delays its greetings and submits victims goes through the sequenced
    slot-exhaustion path, so the victim failure is deterministic. Every other run submits
    concurrently.
    """
    args = build_parser().parse_args()
    greeting_inputs = greeting_inputs_from_args(args)
    victim_inputs = victim_inputs_from_args(args)

    client = await Client.connect(TEMPORAL_TARGET)

    if args.block_seconds > 0 and greeting_inputs and victim_inputs:
        await _run_slot_exhaustion_demo(client, greeting_inputs, victim_inputs)
    else:
        await _run_all_concurrently(client, greeting_inputs, victim_inputs)


if __name__ == "__main__":
    asyncio.run(main())
