"""ABOUTME: Tests for scripts/receipt_gaps.py against receipt histories shaped like workflow show JSON.
ABOUTME: The Temporal CLI is replaced by an injected runner, so no test needs a running server.

The timed-out and healthy fixtures are real `temporal workflow show --output json` captures from a
root `just block` run and a `just healthy` run (2026-11-08), unedited.
receipt-no-activity.json is synthetic and hand-built, because no real receipt completes without an Activity.
receipt-gaps.txt holds the lines the scratchpad gaps.py printed over the same two captured histories.

The fleet-*.json fixtures are real captures from a two-Worker bad flood of the exercise 06 practice copy
(2026-11-11), unedited except that the machine's hostname is replaced by the word `host` in every identity.
Worker 3011940 is the one the flood froze; 3011939 is the healthy one. The fleet-later-timeout.json history is
a receipt whose second Workflow Task timed out twice, so its WT1 is short while its timeouts are not.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from receipt_gaps import (
    IdentityFacts,
    attributes,
    format_history,
    format_identity_line,
    identity_facts,
    main,
    run_temporal,
    summarize_identities,
)

if TYPE_CHECKING:
    from collections.abc import Callable

FIXTURES = Path(__file__).parent / "fixtures"
TIMED_OUT_ID = "receipt-e2cb6ff7-7311-459c-bd3f-03b88846036f"
HEALTHY_ID = "receipt-c35ba6f2-c026-490b-a076-6f9ffabeba39"
NO_ACTIVITY_ID = "receipt-noactivity-0000-0000-000000000000"

FLEET_HEALTHY_ID = "receipt-3c377609-8713-4ccd-9125-92882d4c666f"
FLEET_RETRIED_ID = "receipt-a701c02d-b244-4e65-8d55-cba0a0b9e5bb"
FLEET_FAILED_ID = "receipt-d7700092-ca17-4cc9-96ea-7661283955a5"
FLEET_LATER_TIMEOUT_ID = "receipt-e5c9c7c8-e799-4795-a4d6-7fac31a0a0bd"
FLEET_FIXTURES = {
    FLEET_HEALTHY_ID: "fleet-receipt-healthy.json",
    FLEET_RETRIED_ID: "fleet-receipt-retried.json",
    FLEET_FAILED_ID: "fleet-receipt-failed.json",
    FLEET_LATER_TIMEOUT_ID: "fleet-later-timeout.json",
}
FROZEN = "3011940@host"
HEALTHY_WORKER = "3011939@host"


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


def fleet_runner(listing: list[dict[str, dict[str, str]]] | None = None) -> Callable[[list[str]], str]:
    """Serve the fleet fixtures by Workflow ID, and `listing` for a list call."""

    def runner(args: list[str]) -> str:
        if args[:2] == ["workflow", "list"]:
            return json.dumps(listing)
        return (FIXTURES / FLEET_FIXTURES[args[args.index("-w") + 1]]).read_text()

    return runner


def fleet_facts(workflow_id: str) -> IdentityFacts:
    return identity_facts(load_events(FLEET_FIXTURES[workflow_id]))


def test_default_output_without_new_flags_is_unchanged_byte_for_byte() -> None:
    history_by_id = {
        TIMED_OUT_ID: (FIXTURES / "receipt-timed-out.json").read_text(),
        HEALTHY_ID: (FIXTURES / "receipt-healthy.json").read_text(),
    }
    lines: list[str] = []

    main([TIMED_OUT_ID, HEALTHY_ID], runner=lambda args: history_by_id[args[args.index("-w") + 1]], emit=lines.append)

    assert lines == (FIXTURES / "receipt-gaps.txt").read_text().splitlines()


def test_by_identity_keeps_the_default_line_whole_and_adds_the_first_task_and_activity_identities() -> None:
    events = load_events("fleet-receipt-healthy.json")
    default_line = format_history(FLEET_HEALTHY_ID, events)

    line = format_identity_line(default_line, identity_facts(events))

    assert line == (
        f"{default_line} | wt1 on {FROZEN} attempt 1"
        f" | validate_order on {FROZEN} attempt 1"
        f" | compute_total on {FROZEN} attempt 1"
        f" | format_receipt on {FROZEN} attempt 1"
    )


def test_retried_receipt_names_both_identities_and_the_attempt_that_completed_wt1() -> None:
    facts = fleet_facts(FLEET_RETRIED_ID)

    assert facts.first_identity == FROZEN
    assert facts.wt1_identity == HEALTHY_WORKER
    assert facts.wt1_attempt == 2
    line = format_identity_line("line", facts)
    assert line.startswith(f"line | wt1 on {FROZEN} -> {HEALTHY_WORKER} attempt 2 | ")


def test_workflow_task_timeout_is_attributed_to_the_started_event_before_it() -> None:
    # The rule, read straight off each history: the Started event just before the TimedOut event.
    for name in ("fleet-receipt-retried.json", "fleet-later-timeout.json"):
        events = load_events(name)
        expected = [
            str(attributes(events[index - 1], "workflowTaskStartedEventAttributes")["identity"])
            for index, event in enumerate(events)
            if str(event["eventType"]).endswith("WORKFLOW_TASK_TIMED_OUT")
        ]

        assert identity_facts(events).timeout_identities == tuple(expected)
        assert expected


def test_timeout_on_a_later_workflow_task_is_attributed_though_wt1_is_short() -> None:
    facts = fleet_facts(FLEET_LATER_TIMEOUT_ID)

    assert facts.timeout_identities == (FROZEN, FROZEN)
    assert facts.wt1 is not None
    assert facts.wt1.total_seconds() < 1


def test_timeout_with_no_started_event_is_not_counted_for_a_history_derived_from_the_later_timeout_receipt() -> None:
    events = load_events("fleet-later-timeout.json")
    whole = identity_facts(events).timeout_identities
    timed_out = next(event for event in events if str(event["eventType"]).endswith("WORKFLOW_TASK_TIMED_OUT"))
    scheduled_id = attributes(timed_out, "workflowTaskTimedOutEventAttributes")["scheduledEventId"]

    # A real schedule-to-start timeout carries no started event, so the Started event this timeout points at is dropped.
    derived = [
        event
        for event in events
        if not (
            str(event["eventType"]).endswith("WORKFLOW_TASK_STARTED")
            and attributes(event, "workflowTaskStartedEventAttributes")["scheduledEventId"] == scheduled_id
        )
    ]

    assert len(derived) == len(events) - 1
    assert len(identity_facts(derived).timeout_identities) == len(whole) - 1
    assert identity_facts(derived).timeout_identities == whole[1:]


def test_failed_receipt_marks_the_timed_out_activity_and_attributes_it_through_its_started_event() -> None:
    events = load_events("fleet-receipt-failed.json")
    facts = identity_facts(events)

    line = format_identity_line("line", facts)

    # The Workflow Tasks ran on the healthy Worker; only the ActivityTaskStarted names the frozen one.
    assert line == f"line | wt1 on {HEALTHY_WORKER} attempt 1 | validate_order TIMED OUT on {FROZEN} attempt 2"
    assert facts.first_identity == HEALTHY_WORKER


def test_failed_activity_is_marked_like_a_timed_out_one_for_a_history_derived_from_the_failed_receipt() -> None:
    # No captured history holds an ActivityTaskFailed, so the failed receipt's timeout event is rewritten into one.
    events = copy.deepcopy(load_events("fleet-receipt-failed.json"))
    for event in events:
        if str(event["eventType"]).endswith("ACTIVITY_TASK_TIMED_OUT"):
            event["eventType"] = "EVENT_TYPE_ACTIVITY_TASK_FAILED"
            event["activityTaskFailedEventAttributes"] = event.pop("activityTaskTimedOutEventAttributes")

    line = format_identity_line("line", identity_facts(events))

    assert line.endswith(f"validate_order FAILED on {FROZEN} attempt 2")


def test_summary_over_the_failed_receipt_alone_reads_none_for_a_largest_wt1_the_frozen_identity_never_had() -> None:
    # The frozen Worker only holds the timed-out Activity here: it started no first Workflow Task, so it has no WT1.
    assert summarize_identities([fleet_facts(FLEET_FAILED_ID)]) == [
        f"{HEALTHY_WORKER}: first Workflow Tasks 1 | Workflow Task timeouts 0 | Activities failed 0 | largest WT1 31ms",
        f"{FROZEN}: first Workflow Tasks 0 | Workflow Task timeouts 0 | Activities failed 1 | largest WT1 none",
    ]


def test_activity_with_no_started_event_reads_on_no_worker_for_a_history_derived_from_the_failed_receipt() -> None:
    events = load_events("fleet-receipt-failed.json")
    timed_out = next(event for event in events if str(event["eventType"]).endswith("ACTIVITY_TASK_TIMED_OUT"))
    scheduled_id = attributes(timed_out, "activityTaskTimedOutEventAttributes")["scheduledEventId"]

    # Drop the ActivityTaskStarted that shares the timed-out Activity's scheduled event id.
    derived = [
        event
        for event in events
        if not (
            str(event["eventType"]).endswith("ACTIVITY_TASK_STARTED")
            and attributes(event, "activityTaskStartedEventAttributes")["scheduledEventId"] == scheduled_id
        )
    ]
    facts = identity_facts(derived)

    assert len(derived) == len(events) - 1
    assert format_identity_line("line", facts).endswith("| validate_order TIMED OUT on no Worker")
    # With no identity to charge, the failed Activity is counted for nobody.
    assert summarize_identities([facts]) == [
        f"{HEALTHY_WORKER}: first Workflow Tasks 1 | Workflow Task timeouts 0 | Activities failed 0 | largest WT1 31ms",
    ]


def test_per_identity_summary_counts_first_tasks_timeouts_failed_activities_and_largest_wt1() -> None:
    all_facts = [fleet_facts(workflow_id) for workflow_id in FLEET_FIXTURES]

    assert summarize_identities(all_facts) == [
        f"{HEALTHY_WORKER}: first Workflow Tasks 1 | Workflow Task timeouts 0 | Activities failed 0 | largest WT1 31ms",
        f"{FROZEN}: first Workflow Tasks 3 | Workflow Task timeouts 3 | Activities failed 1 | largest WT1 10139ms",
    ]


def test_summary_with_by_identity_prints_the_summary_lines_alone() -> None:
    lines: list[str] = []

    main(list(FLEET_FIXTURES) + ["--by-identity", "--summary"], runner=fleet_runner(), emit=lines.append)

    assert len(lines) == 2
    assert all(": first Workflow Tasks " in line for line in lines)


def test_summary_without_by_identity_is_rejected_with_a_clear_message(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--summary", FLEET_HEALTHY_ID], runner=fleet_runner(), emit=lambda _line: None)

    assert exit_info.value.code == 2
    assert "--summary is valid only with --by-identity" in capsys.readouterr().err


def test_limit_with_by_identity_and_summary_emits_exactly_the_per_identity_lines() -> None:
    listing = [
        {"type": {"name": "GeoEnrichmentWorkflow"}, "execution": {"workflowId": "geo-1"}},
        {"type": {"name": "OrderReceiptWorkflow"}, "execution": {"workflowId": FLEET_HEALTHY_ID}},
        {"type": {"name": "OrderReceiptWorkflow"}, "execution": {"workflowId": FLEET_RETRIED_ID}},
        {"type": {"name": "OrderReceiptWorkflow"}, "execution": {"workflowId": FLEET_FAILED_ID}},
        {"type": {"name": "OrderReceiptWorkflow"}, "execution": {"workflowId": FLEET_LATER_TIMEOUT_ID}},
    ]
    lines: list[str] = []

    exit_code = main(["--limit", "5", "--by-identity", "--summary"], runner=fleet_runner(listing), emit=lines.append)

    assert exit_code == 0
    assert lines == [
        f"{HEALTHY_WORKER}: first Workflow Tasks 1 | Workflow Task timeouts 0 | Activities failed 0 | largest WT1 31ms",
        f"{FROZEN}: first Workflow Tasks 3 | Workflow Task timeouts 3 | Activities failed 1 | largest WT1 10139ms",
    ]


def test_by_identity_without_summary_prints_each_line_then_the_summary() -> None:
    lines: list[str] = []

    main([FLEET_FAILED_ID, FLEET_RETRIED_ID, "--by-identity"], runner=fleet_runner(), emit=lines.append)

    assert [line.split(" ", 1)[0] for line in lines[:2]] == ["receipt-d7700092", "receipt-a701c02d"]
    assert lines[1].endswith(
        f"| validate_order on {HEALTHY_WORKER} attempt 1 | compute_total on {HEALTHY_WORKER} attempt 1"
        f" | format_receipt on {HEALTHY_WORKER} attempt 1"
    )
    assert lines[2:] == [
        f"{HEALTHY_WORKER}: first Workflow Tasks 1 | Workflow Task timeouts 0 | Activities failed 0 | largest WT1 31ms",
        f"{FROZEN}: first Workflow Tasks 1 | Workflow Task timeouts 1 | Activities failed 1 | largest WT1 10139ms",
    ]
