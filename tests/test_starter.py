"""ABOUTME: CLI-contract tests for the starter's argument parser, input helpers, and metrics parser.
ABOUTME: No test touches a Temporal server; main()'s live submission is exercised manually.

These tests pin the flag names, defaults, and choices, prove that the count flags fan out into the
right workflow inputs, and check that the metrics parser reads the ActivityWorker slot gauge rather
than the LocalActivityWorker line.
"""

from __future__ import annotations

import pytest

from temporal_async_debug.shared import GeoEnrichmentInput, OrderReceiptInput
from temporal_async_debug.starter import (
    bad_geo_inputs_from_args,
    build_parser,
    healthy_geo_inputs_from_args,
    parse_activity_slots_available,
    receipt_inputs_from_args,
)

_LABELS = 'namespace="default",service_name="temporal-core-sdk",task_queue="async-debug-task-queue"'
"""The label set the real worker emits, shared by the metrics-parsing fixtures below."""


def _metrics_page(activity_free: int) -> str:
    """Build a metrics page with the given ActivityWorker free-slot count.

    The LocalActivityWorker line is included on purpose: its label contains "ActivityWorker" as a
    substring, so parsing must not pick it up by mistake.
    """
    return (
        "# HELP temporal_worker_task_slots_available Current number of available slots per task type\n"
        "# TYPE temporal_worker_task_slots_available gauge\n"
        f'temporal_worker_task_slots_available{{{_LABELS},worker_type="ActivityWorker"}} {activity_free}\n'
        f'temporal_worker_task_slots_available{{{_LABELS},worker_type="LocalActivityWorker"}} 100\n'
        f'temporal_worker_task_slots_available{{{_LABELS},worker_type="WorkflowWorker"}} 100\n'
    )


def test_flag_defaults() -> None:
    """With no flags, the parser applies the documented healthy defaults."""
    args = build_parser().parse_args([])

    assert args.mode == "block"
    assert args.block_seconds == 0.0
    assert args.bad == 0
    assert args.geo == 0
    assert args.receipts == 0


def test_mode_rejects_invalid_value() -> None:
    """--mode is restricted to the two known modes; anything else exits via argparse."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--mode", "sideways"])


@pytest.mark.parametrize("mode", ["block", "slow"])
def test_mode_accepts_known_values(mode: str) -> None:
    """Both documented modes parse without error."""
    assert build_parser().parse_args(["--mode", mode]).mode == mode


def test_numeric_flags_parse_to_their_types() -> None:
    """--block-seconds parses as float; --bad, --geo, and --receipts parse as int."""
    args = build_parser().parse_args(["--block-seconds", "1.5", "--bad", "2", "--geo", "4", "--receipts", "7"])

    assert isinstance(args.block_seconds, float)
    assert args.block_seconds == 1.5
    assert args.bad == 2
    assert args.geo == 4
    assert args.receipts == 7


def test_bad_geo_inputs_carry_mode_and_block_seconds() -> None:
    """--bad 2 yields two GeoEnrichmentInput values, each carrying the parsed mode and block_seconds."""
    args = build_parser().parse_args(["--mode", "slow", "--block-seconds", "30", "--bad", "2"])

    bad_inputs = bad_geo_inputs_from_args(args)

    assert len(bad_inputs) == 2
    assert all(isinstance(bad_input, GeoEnrichmentInput) for bad_input in bad_inputs)
    assert all(bad_input.mode == "slow" for bad_input in bad_inputs)
    assert all(bad_input.block_seconds == 30.0 for bad_input in bad_inputs)


def test_healthy_geo_inputs_have_no_delay() -> None:
    """--geo 3 yields three healthy GeoEnrichmentInput values with no delay."""
    args = build_parser().parse_args(["--geo", "3"])

    healthy_inputs = healthy_geo_inputs_from_args(args)

    assert len(healthy_inputs) == 3
    assert all(healthy_input.block_seconds == 0.0 for healthy_input in healthy_inputs)


def test_receipt_inputs_have_distinct_order_ids() -> None:
    """--receipts 3 yields three OrderReceiptInput values with distinct order ids."""
    args = build_parser().parse_args(["--receipts", "3"])

    receipt_inputs = receipt_inputs_from_args(args)

    assert len(receipt_inputs) == 3
    assert all(isinstance(receipt_input, OrderReceiptInput) for receipt_input in receipt_inputs)
    order_ids = [receipt_input.order_id for receipt_input in receipt_inputs]
    assert len(set(order_ids)) == 3


def test_counts_default_to_empty_fleets() -> None:
    """The defaults produce no workflows of any kind."""
    args = build_parser().parse_args([])

    assert bad_geo_inputs_from_args(args) == []
    assert healthy_geo_inputs_from_args(args) == []
    assert receipt_inputs_from_args(args) == []


@pytest.mark.parametrize("activity_free", [0, 1, 2])
def test_parse_activity_slots_reads_the_activity_worker_gauge(activity_free: int) -> None:
    """The parser returns the ActivityWorker free-slot value, not the LocalActivityWorker one."""
    assert parse_activity_slots_available(_metrics_page(activity_free)) == activity_free


def test_parse_activity_slots_returns_none_when_absent() -> None:
    """A metrics page without the activity slot gauge yields None, not a crash or a wrong reading."""
    assert parse_activity_slots_available("# nothing relevant here\n") is None
