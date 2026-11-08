"""ABOUTME: Tests for scripts/receipt_gaps.py against receipt histories shaped like workflow show JSON.
ABOUTME: The Temporal CLI is replaced by an injected runner, so no test needs a running server.

The timed-out and healthy fixtures are real `temporal workflow show --output json` captures from a
root `just block` run and a `just healthy` run (2026-11-08), unedited.
receipt-no-activity.json is synthetic and hand-built, because no real receipt completes without an Activity.
receipt-gaps.txt holds the lines the scratchpad gaps.py printed over the same two captured histories.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from receipt_gaps import attributes, format_history, main, run_temporal

FIXTURES = Path(__file__).parent / "fixtures"
TIMED_OUT_ID = "receipt-e2cb6ff7-7311-459c-bd3f-03b88846036f"
HEALTHY_ID = "receipt-c35ba6f2-c026-490b-a076-6f9ffabeba39"
NO_ACTIVITY_ID = "receipt-noactivity-0000-0000-000000000000"


def load_events(name: str) -> list[dict[str, object]]:
    history = json.loads((FIXTURES / name).read_text())
    events: list[dict[str, object]] = history["events"]
    return events


def test_timed_out_receipt_wt1_spans_the_timeout_and_retry() -> None:
    # First WorkflowTaskStarted at 17:25:00.2636, first WorkflowTaskCompleted at 17:25:29.0915 (28828 ms later).
    # A last-Workflow-Task definition would read about 9 ms instead.
    line = format_history(TIMED_OUT_ID, load_events("receipt-timed-out.json"))

    assert line.startswith("receipt-e2cb6ff7 total 28913ms | WT1 started->completed 28828ms | ")


def test_healthy_receipt_reports_wt1_and_every_activity_gap() -> None:
    line = format_history(HEALTHY_ID, load_events("receipt-healthy.json"))

    assert line == (
        "receipt-c35ba6f2 total 602ms | WT1 started->completed 21ms"
        " | validate_order: sched->started 193ms started->completed 5ms"
        " | compute_total: sched->started 189ms started->completed 6ms"
        " | format_receipt: sched->started 104ms started->completed 15ms"
    )


def test_history_without_an_activity_still_prints_wt1_and_total() -> None:
    line = format_history(NO_ACTIVITY_ID, load_events("receipt-no-activity.json"))

    assert line == "receipt-noactivi total 12ms | WT1 started->completed 7ms"


def test_limit_listing_keeps_only_order_receipt_workflows() -> None:
    listing = [
        {"type": {"name": "GeoEnrichmentWorkflow"}, "execution": {"workflowId": "geo-1"}},
        {"type": {"name": "OrderReceiptWorkflow"}, "execution": {"workflowId": HEALTHY_ID}},
        {"type": {"name": "SalesRollupWorkflow"}, "execution": {"workflowId": "rollup-1"}},
    ]
    healthy_history = (FIXTURES / "receipt-healthy.json").read_text()
    calls: list[list[str]] = []

    def fake_runner(args: list[str]) -> str:
        calls.append(args)
        if args[:2] == ["workflow", "list"]:
            return json.dumps(listing)
        return healthy_history

    lines: list[str] = []
    exit_code = main(["--limit", "3"], runner=fake_runner, emit=lines.append)

    assert exit_code == 0
    assert len(lines) == 1
    assert lines[0].startswith("receipt-c35ba6f2 ")
    assert ["workflow", "list", "--limit", "3", "--output", "json"] in calls
    assert [call for call in calls if call[:2] == ["workflow", "show"]] == [
        ["workflow", "show", "-w", HEALTHY_ID, "--output", "json"]
    ]


def test_workflow_ids_are_shown_directly() -> None:
    calls: list[list[str]] = []
    timed_out_history = (FIXTURES / "receipt-timed-out.json").read_text()

    def fake_runner(args: list[str]) -> str:
        calls.append(args)
        return timed_out_history

    lines: list[str] = []
    main([TIMED_OUT_ID], runner=fake_runner, emit=lines.append)

    assert len(calls) == 1
    assert len(lines) == 1


def test_fixture_histories_reproduce_the_captured_receipt_gap_lines() -> None:
    # receipt-gaps.txt is gaps.py output over the same captured JSON, not derived from this script.
    captured = {line.split(" ", 1)[0]: line for line in (FIXTURES / "receipt-gaps.txt").read_text().splitlines()}
    fixture_ids = {
        "receipt-timed-out.json": TIMED_OUT_ID,
        "receipt-healthy.json": HEALTHY_ID,
    }

    for name, workflow_id in fixture_ids.items():
        assert format_history(workflow_id, load_events(name)) == captured[workflow_id[:16]]


def test_failing_temporal_call_surfaces_stderr(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, args, output="", stderr="workflow not found")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(SystemExit, match="workflow not found"):
        run_temporal(["workflow", "show", "-w", "missing"])


def test_attributes_rejects_a_non_object_value() -> None:
    with pytest.raises(ValueError, match="eventTime is not an object"):
        attributes({"eventTime": "2026-01-01T00:00:00Z"}, "eventTime")
