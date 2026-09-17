"""ABOUTME: CLI-contract tests for the starter's argument parser and input-construction helpers.
ABOUTME: No test touches a Temporal server; main()'s live submission is exercised manually.

These tests pin the flag names, defaults, types, and choices, and prove that count and victims
fan out into the right number of workflow inputs. They cover our CLI surface, not argparse itself.
"""

from __future__ import annotations

import pytest

from temporal_async_debug.shared import GreetingInput, VictimInput
from temporal_async_debug.starter import (
    build_parser,
    greeting_inputs_from_args,
    victim_inputs_from_args,
)


def test_flag_defaults() -> None:
    """With no flags, the parser applies the documented healthy defaults."""
    args = build_parser().parse_args([])

    assert isinstance(args.name, str)
    assert args.name != ""
    assert args.block_seconds == 0.0
    assert args.mode == "block"
    assert args.count == 1
    assert args.victims == 0


def test_mode_rejects_invalid_value() -> None:
    """--mode is restricted to the two known modes; anything else exits via argparse."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--mode", "sideways"])


@pytest.mark.parametrize("mode", ["block", "slow"])
def test_mode_accepts_known_values(mode: str) -> None:
    """Both documented modes parse without error."""
    args = build_parser().parse_args(["--mode", mode])

    assert args.mode == mode


def test_numeric_flags_parse_to_their_types() -> None:
    """--block-seconds parses as float; --count and --victims parse as int."""
    args = build_parser().parse_args(["--block-seconds", "1.5", "--count", "4", "--victims", "7"])

    assert isinstance(args.block_seconds, float)
    assert args.block_seconds == 1.5
    assert isinstance(args.count, int)
    assert args.count == 4
    assert isinstance(args.victims, int)
    assert args.victims == 7


def test_full_flag_round_trip() -> None:
    """A full flag set parses to exactly the typed values, with correct types."""
    args = build_parser().parse_args(
        ["--name", "ada", "--mode", "slow", "--block-seconds", "30", "--count", "2", "--victims", "3"]
    )

    assert args.name == "ada"
    assert args.mode == "slow"
    assert args.block_seconds == 30.0
    assert args.count == 2
    assert args.victims == 3


def test_greeting_inputs_carry_mode_and_block_seconds() -> None:
    """--count 2 yields two GreetingInput values, each carrying the parsed mode and block_seconds."""
    args = build_parser().parse_args(["--name", "ada", "--mode", "slow", "--block-seconds", "30", "--count", "2"])

    greeting_inputs = greeting_inputs_from_args(args)

    assert len(greeting_inputs) == 2
    assert all(isinstance(greeting_input, GreetingInput) for greeting_input in greeting_inputs)
    assert all(greeting_input.name == "ada" for greeting_input in greeting_inputs)
    assert all(greeting_input.mode == "slow" for greeting_input in greeting_inputs)
    assert all(greeting_input.block_seconds == 30.0 for greeting_input in greeting_inputs)


def test_victim_inputs_have_distinct_labels() -> None:
    """--victims 3 yields three VictimInput values with distinct labels."""
    args = build_parser().parse_args(["--victims", "3"])

    victim_inputs = victim_inputs_from_args(args)

    assert len(victim_inputs) == 3
    assert all(isinstance(victim_input, VictimInput) for victim_input in victim_inputs)
    labels = [victim_input.label for victim_input in victim_inputs]
    assert len(set(labels)) == 3


def test_count_and_victims_default_to_single_and_none() -> None:
    """The defaults produce one greeting input and zero victim inputs."""
    args = build_parser().parse_args([])

    assert len(greeting_inputs_from_args(args)) == 1
    assert victim_inputs_from_args(args) == []
