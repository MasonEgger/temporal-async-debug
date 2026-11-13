"""ABOUTME: Tests for the worker's construction and startup banner, with no live Temporal server.
ABOUTME: build_worker runs against the time-skipping environment's client; the banner runs under capsys.

These tests pin the setup the tutorial depends on: two activity slots (small on purpose), no
activity_executor (so async activities share the one event loop), and every workflow type and
activity registered on the one worker so a failure in one type can reach the others.
"""

from __future__ import annotations

import io
import os
import sys
from typing import TYPE_CHECKING

from temporalio.testing import WorkflowEnvironment

from temporal_async_debug.receipt import OrderReceiptWorkflow
from temporal_async_debug.rollup import SalesRollupWorkflow
from temporal_async_debug.shared import TASK_QUEUE
from temporal_async_debug.worker import build_worker, print_startup_banner
from temporal_async_debug.workflow import GeoEnrichmentWorkflow

if TYPE_CHECKING:
    import pytest

EXPECTED_ACTIVITY_NAMES: frozenset[str] = frozenset(
    {
        "get_ip",
        "get_location",
        "validate_order",
        "compute_total",
        "format_receipt",
        "roll_up_sales",
    }
)
"""Every activity the three workflow types schedule, all of which must share the one worker."""


async def test_build_worker_keeps_the_small_slot_pool_and_full_registration() -> None:
    """build_worker caps activity slots at two, adds no executor, and registers the whole fleet."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        worker_config = build_worker(env.client).config()

    assert worker_config.get("task_queue") == TASK_QUEUE
    assert worker_config.get("max_concurrent_activities") == 2
    assert worker_config.get("activity_executor") is None
    registered_activity_names = {activity_fn.__name__ for activity_fn in worker_config.get("activities", [])}
    assert registered_activity_names == EXPECTED_ACTIVITY_NAMES
    assert set(worker_config.get("workflows", [])) == {
        GeoEnrichmentWorkflow,
        OrderReceiptWorkflow,
        SalesRollupWorkflow,
    }


def test_print_startup_banner_shows_the_pid_and_both_introspection_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The banner carries the real PID inside copy-paste asyncio ps and pstree commands."""
    print_startup_banner()

    banner = capsys.readouterr().out
    pid = os.getpid()
    assert f"PID {pid}" in banner
    assert f"python -m asyncio ps {pid}" in banner
    assert f"python -m asyncio pstree {pid}" in banner


def test_print_startup_banner_reaches_a_block_buffered_stdout_without_an_explicit_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under nohup or a log redirect stdout is block-buffered, so the banner must flush itself."""
    captured_bytes = io.BytesIO()
    block_buffered_stdout = io.TextIOWrapper(io.BufferedWriter(captured_bytes, buffer_size=65_536), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", block_buffered_stdout)

    print_startup_banner()

    assert f"PID {os.getpid()}".encode() in captured_bytes.getvalue()
