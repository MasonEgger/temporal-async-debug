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
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from temporalio.client import Client

from temporal_async_debug.shared import TASK_QUEUE, GreetingInput, VictimInput
from temporal_async_debug.victim import VictimWorkflow
from temporal_async_debug.workflow import GreetingWorkflow

TEMPORAL_TARGET: str = "localhost:7233"
"""Address of the local Temporal dev server the starter submits to."""


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


async def main() -> None:
    """Parse the CLI flags, connect to the local server, and submit every run concurrently.

    Builds the greeting and victim inputs from the parsed flags, connects a Client to the local
    dev server, submits all greeting and victim workflows concurrently with asyncio.gather, awaits
    every result, and prints each one.
    """
    args = build_parser().parse_args()
    greeting_inputs = greeting_inputs_from_args(args)
    victim_inputs = victim_inputs_from_args(args)

    client = await Client.connect(TEMPORAL_TARGET)

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


if __name__ == "__main__":
    asyncio.run(main())
