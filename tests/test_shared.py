"""ABOUTME: Contract tests for the shared workflow payloads and the task queue constant.
ABOUTME: Pins the healthy defaults, the frozen payloads, and the exact task queue name.
"""

import dataclasses

import pytest

from temporal_async_debug.shared import (
    TASK_QUEUE,
    GreetingInput,
    GreetingOutput,
    VictimInput,
    VictimOutput,
)


def test_greeting_input_block_seconds_defaults_to_zero() -> None:
    """A GreetingInput built with only a name applies no mode delay."""
    assert GreetingInput(name="ada").block_seconds == 0.0


def test_greeting_input_mode_defaults_to_block() -> None:
    """Mode defaults to "block", so only a switch to "slow" needs an explicit flag."""
    assert GreetingInput(name="ada").mode == "block"


@pytest.mark.parametrize(
    ("payload", "attribute"),
    [
        (GreetingInput(name="ada"), "name"),
        (GreetingOutput(ip="203.0.113.7", location="Austin, Texas", greeting="Hello, ada"), "ip"),
        (VictimInput(label="victim-1"), "label"),
        (VictimOutput(message="victim-1 finished"), "message"),
    ],
)
def test_workflow_payloads_are_frozen(payload: object, attribute: str) -> None:
    """Every payload crossing the workflow boundary rejects mutation after construction."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(payload, attribute, "mutated")


def test_greeting_input_round_trips_explicit_values() -> None:
    """Explicit values survive construction, and the positional field order is name, seconds, mode."""
    greeting_input = GreetingInput(name="ada", block_seconds=30.0, mode="slow")

    assert greeting_input.name == "ada"
    assert greeting_input.block_seconds == 30.0
    assert greeting_input.mode == "slow"
    assert greeting_input == GreetingInput("ada", 30.0, "slow")


def test_task_queue_name_is_stable() -> None:
    """The worker and the starter agree on this exact task queue name."""
    assert TASK_QUEUE == "async-debug-task-queue"
