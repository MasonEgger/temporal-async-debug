"""ABOUTME: Frozen payload dataclasses and the task queue name shared across the demo.
ABOUTME: Both workflows, their activities, the worker, and the starter import from here.

Every payload here crosses the Temporal workflow boundary, so each one stays small,
frozen, and JSON-serializable. ``GreetingInput`` also carries the two knobs that drive
the demo's failure modes: how long an activity delays, and which kind of delay it uses.
"""

from __future__ import annotations

from dataclasses import dataclass

TASK_QUEUE: str = "async-debug-task-queue"
"""Task queue that the worker polls and the starter submits to."""


@dataclass(frozen=True)
class GreetingInput:
    """Input to GreetingWorkflow, the deliberately misbehaving workflow.

    Attributes:
        name: Name to greet.
        block_seconds: Seconds of delay each activity applies before its HTTP call.
            Defaults to 0.0, the healthy value, meaning no delay at all.
        mode: Which delay to apply when block_seconds is above zero. "block" calls
            time.sleep, which freezes the worker's event loop and is the deliberate
            bug this demo teaches. "slow" awaits asyncio.sleep, which is cooperative
            but still holds an activity slot for the duration.
    """

    name: str
    block_seconds: float = 0.0
    mode: str = "block"


@dataclass(frozen=True)
class GreetingOutput:
    """Result of GreetingWorkflow, assembled from both activity results.

    Attributes:
        ip: Public IP address returned by the get_ip activity.
        location: Human-readable location returned by the get_location activity.
        greeting: Final greeting built from the name, the IP, and the location.
    """

    ip: str
    location: str
    greeting: str


@dataclass(frozen=True)
class VictimInput:
    """Input to VictimWorkflow, the innocent workflow sharing the worker.

    Attributes:
        label: Identifier that distinguishes one concurrent victim run from another.
    """

    label: str


@dataclass(frozen=True)
class VictimOutput:
    """Result of VictimWorkflow.

    Attributes:
        message: Confirmation that the victim's quick task ran to completion.
    """

    message: str
