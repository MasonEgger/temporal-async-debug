"""ABOUTME: Prints the receipt-gap figures the tutorial quotes for each OrderReceiptWorkflow run.
ABOUTME: Reads `temporal workflow show --output json` histories; stdlib only, no running Worker needed.

"WT1" is the span from the first WorkflowTaskStarted to the first WorkflowTaskCompleted.
When the Worker's event loop is frozen, the first Workflow Task goes out, times out, and is retried
after the thaw, so WT1 covers the timeout and its retry. That span is the stall a receipt feels,
and it is why WT1 uses the first Workflow Task, not the last.
Each Activity reports scheduled-to-started and started-to-completed, in milliseconds.

Run it from the repository root, or from any exercise directory with the path adjusted:

    just receipt-gaps --limit 5
    just receipt-gaps receipt-0ad58652-e4de-4a20-b741-d894fbbaa521
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime

Runner = Callable[[list[str]], str]
Event = dict[str, object]


def run_temporal(args: list[str]) -> str:
    """Run the Temporal CLI and return its standard output."""
    try:
        return subprocess.run(["temporal", *args], check=True, capture_output=True, text=True).stdout
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"temporal {' '.join(args)} failed with exit code {error.returncode}: {error.stderr.strip()}"
        ) from error


def event_time(event: Event) -> datetime:
    """Parse an event's eventTime (RFC 3339 with a Z suffix) into an aware datetime."""
    return datetime.fromisoformat(str(event["eventTime"]).replace("Z", "+00:00"))


def milliseconds(start: datetime, end: datetime) -> str:
    """Format the span between two datetimes as whole milliseconds, e.g. '28786ms'."""
    return f"{(end - start).total_seconds() * 1000:.0f}ms"


def attributes(event: Event, key: str) -> Event:
    """Return the nested attributes object stored under `key` on an event."""
    value = event[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} is not an object")
    return value


def format_history(workflow_id: str, events: list[Event]) -> str:
    """Build the one-line gap report for a single Workflow history.

    Args:
        workflow_id: The Workflow ID; the first 16 characters label the line.
        events: The `events` list from `temporal workflow show --output json`.

    Returns:
        The total duration, the WT1 gap when the history has one, and one entry per completed Activity.
    """
    scheduled: dict[str, tuple[str, datetime]] = {}
    started: dict[str, datetime] = {}
    first_task_started: datetime | None = None
    wt1: str | None = None
    parts: list[str] = []
    for event in events:
        kind = str(event["eventType"])
        when = event_time(event)
        if kind.endswith("ACTIVITY_TASK_SCHEDULED"):
            activity_type = attributes(attributes(event, "activityTaskScheduledEventAttributes"), "activityType")
            scheduled[str(event["eventId"])] = (str(activity_type["name"]), when)
        elif kind.endswith("ACTIVITY_TASK_STARTED"):
            started[str(attributes(event, "activityTaskStartedEventAttributes")["scheduledEventId"])] = when
        elif kind.endswith("ACTIVITY_TASK_COMPLETED"):
            scheduled_id = str(attributes(event, "activityTaskCompletedEventAttributes")["scheduledEventId"])
            name, scheduled_at = scheduled[scheduled_id]
            parts.append(
                f"{name}: sched->started {milliseconds(scheduled_at, started[scheduled_id])}"
                f" started->completed {milliseconds(started[scheduled_id], when)}"
            )
        elif kind.endswith("WORKFLOW_TASK_STARTED") and first_task_started is None:
            first_task_started = when
        elif kind.endswith("WORKFLOW_TASK_COMPLETED") and first_task_started is not None and wt1 is None:
            wt1 = f"WT1 started->completed {milliseconds(first_task_started, when)}"
    total = milliseconds(event_time(events[0]), event_time(events[-1]))
    return f"{workflow_id[:16]} total {total} | " + " | ".join([wt1, *parts] if wt1 else parts)


def receipt_ids(limit: str, runner: Runner) -> list[str]:
    """List the newest `limit` Workflows and keep the OrderReceiptWorkflow IDs."""
    listing = json.loads(runner(["workflow", "list", "--limit", limit, "--output", "json"]))
    return [
        str(entry["execution"]["workflowId"]) for entry in listing if entry["type"]["name"] == "OrderReceiptWorkflow"
    ]


def main(argv: Sequence[str] | None = None, runner: Runner = run_temporal, emit: Callable[[str], None] = print) -> int:
    """Print one gap line per receipt Workflow named by ID or found by `--limit`."""
    parser = argparse.ArgumentParser(description="Print WT1 and Activity gaps for OrderReceiptWorkflow runs.")
    parser.add_argument("workflow_ids", nargs="*", help="Workflow IDs to inspect")
    parser.add_argument("--limit", help="inspect the OrderReceiptWorkflow runs among the newest N Workflows")
    args = parser.parse_args(argv)
    workflow_ids = list(args.workflow_ids)
    if args.limit:
        workflow_ids += receipt_ids(args.limit, runner)
    for workflow_id in workflow_ids:
        history = json.loads(runner(["workflow", "show", "-w", workflow_id, "--output", "json"]))
        emit(format_history(workflow_id, history["events"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
