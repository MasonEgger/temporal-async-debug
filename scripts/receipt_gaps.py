"""ABOUTME: Prints the receipt-gap figures the tutorial quotes for each OrderReceiptWorkflow run.
ABOUTME: Reads `temporal workflow show --output json` histories; stdlib only, no running Worker needed.

"WT1" is the span from the first WorkflowTaskStarted to the first WorkflowTaskCompleted.
When the Worker's event loop is frozen, the first Workflow Task goes out, times out, and is retried
after the thaw, so WT1 covers the timeout and its retry. That span is the stall a receipt feels,
and it is why WT1 uses the first Workflow Task, not the last.
Each Activity reports scheduled-to-started and started-to-completed, in milliseconds.

`just receipt-gaps` runs the script from the repository root with `uv run python scripts/receipt_gaps.py`
and passes its arguments through, so any flag below works after the recipe name:

    just receipt-gaps --limit 5
    just receipt-gaps receipt-0ad58652-e4de-4a20-b741-d894fbbaa521
    just receipt-gaps --limit 600 --by-identity
    just receipt-gaps --limit 600 --by-identity --summary

--by-identity groups what a history shows by the Worker identity (PID@hostname by default) on its Started events. Each
line keeps its default text and gains: "wt1 on" the identity on the first WorkflowTaskStarted, then "->" the identity
that completed WT1 only when that Workflow Task ran on a different identity, then "attempt N" from the
WorkflowTaskScheduled that completed WT1 (printed on every line that has a WT1, so a healthy line reads "attempt 1"),
one entry per WorkflowTaskTimedOut that has a WorkflowTaskStarted, and one entry per Activity with its identity and
attempt. An Activity that timed out or failed is marked. WorkflowTaskTimedOut carries no identity, so a timeout
belongs to the identity on the WorkflowTaskStarted before it (the one that shares its scheduled event id), whether the
timeout hit the first Workflow Task or a later one. A Workflow Task that timed out before any Worker started it (a
schedule-to-start timeout, which has no Started event and so no identity) is not counted. A timed-out or failed
Activity belongs to the identity on the ActivityTaskStarted that shares its scheduled event id. After the lines, one
summary line per identity counts the first Workflow Tasks it started, the Workflow Task timeouts it holds, the
Activities that failed on it, and its largest WT1.

--summary, valid only with --by-identity, prints those summary lines alone.

Limit: a retried Activity's history keeps only its last attempt's ActivityTaskStarted. An attempt that a
frozen Worker swallowed and that then ran again elsewhere leaves no event naming the frozen identity, so
the identity view does not count it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

Runner = Callable[[list[str]], str]
Event = dict[str, object]

ACTIVITY_OUTCOMES = {
    "ACTIVITY_TASK_COMPLETED": ("completed", "activityTaskCompletedEventAttributes"),
    "ACTIVITY_TASK_TIMED_OUT": ("timed out", "activityTaskTimedOutEventAttributes"),
    "ACTIVITY_TASK_FAILED": ("failed", "activityTaskFailedEventAttributes"),
}
"""Terminal Activity event types, each with its outcome label and the attributes key that holds its scheduledEventId."""


@dataclass(frozen=True)
class ActivityFact:
    """One Activity that reached a terminal event, with the Worker that started it.

    Attributes:
        name: The Activity type name.
        outcome: "completed", "timed out", or "failed".
        identity: The identity on the ActivityTaskStarted that shares the Activity's scheduled event id, or
            None when the history holds no such event (an Activity that timed out before any Worker took it).
        attempt: The attempt recorded on that ActivityTaskStarted, or None with it.
    """

    name: str
    outcome: str
    identity: str | None
    attempt: int | None


@dataclass(frozen=True)
class IdentityFacts:
    """The Worker identities one history names, reduced from its events.

    Attributes:
        first_identity: The identity on the first WorkflowTaskStarted, or None for a history with none.
        wt1: The span from the first WorkflowTaskStarted to the first WorkflowTaskCompleted, or None.
        wt1_identity: The identity on the WorkflowTaskStarted that completed WT1, or None with `wt1`.
        wt1_attempt: The attempt on the WorkflowTaskScheduled that completed WT1, or None with `wt1`.
        timeout_identities: One identity per WorkflowTaskTimedOut that has a WorkflowTaskStarted, in history order.
        activities: One entry per Activity that completed, timed out, or failed, in history order.
    """

    first_identity: str | None
    wt1: timedelta | None
    wt1_identity: str | None
    wt1_attempt: int | None
    timeout_identities: tuple[str, ...]
    activities: tuple[ActivityFact, ...]


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


def span_ms(span: timedelta) -> str:
    """Format a span as whole milliseconds, e.g. '28786ms'."""
    return f"{span.total_seconds() * 1000:.0f}ms"


def milliseconds(start: datetime, end: datetime) -> str:
    """Format the span between two datetimes as whole milliseconds, e.g. '28786ms'."""
    return span_ms(end - start)


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


def identity_facts(events: list[Event]) -> IdentityFacts:
    """Reduce one history to the Worker identities it names.

    A WorkflowTaskTimedOut carries no identity, so it is attributed to the identity on the
    WorkflowTaskStarted that shares its scheduled event id (the Started event before it). A timed-out
    or failed Activity is attributed through the ActivityTaskStarted that shares its scheduled event id.
    A retried Activity's history keeps only its last attempt's ActivityTaskStarted, so an attempt that a
    frozen Worker swallowed before a retry completed elsewhere is not counted.

    Args:
        events: The `events` list from `temporal workflow show --output json`.

    Returns:
        The identity facts; fields are None or empty when the history holds no matching event.
    """
    task_identity: dict[str, str] = {}
    task_attempt: dict[str, int] = {}
    activity_name: dict[str, str] = {}
    activity_start: dict[str, tuple[str, int]] = {}
    first_started: tuple[str, datetime] | None = None
    wt1: tuple[timedelta, str, int] | None = None
    timeouts: list[str] = []
    activities: list[ActivityFact] = []
    for event in events:
        kind = str(event["eventType"]).removeprefix("EVENT_TYPE_")
        if kind == "WORKFLOW_TASK_SCHEDULED":
            task_attempt[str(event["eventId"])] = int(
                str(attributes(event, "workflowTaskScheduledEventAttributes")["attempt"])
            )
        elif kind == "WORKFLOW_TASK_STARTED":
            details = attributes(event, "workflowTaskStartedEventAttributes")
            task_identity[str(details["scheduledEventId"])] = str(details["identity"])
            if first_started is None:
                first_started = (str(details["identity"]), event_time(event))
        elif kind == "WORKFLOW_TASK_COMPLETED" and first_started is not None and wt1 is None:
            scheduled_id = str(attributes(event, "workflowTaskCompletedEventAttributes")["scheduledEventId"])
            wt1 = (event_time(event) - first_started[1], task_identity[scheduled_id], task_attempt[scheduled_id])
        elif kind == "WORKFLOW_TASK_TIMED_OUT":
            scheduled_id = str(attributes(event, "workflowTaskTimedOutEventAttributes")["scheduledEventId"])
            if scheduled_id in task_identity:
                timeouts.append(task_identity[scheduled_id])
        elif kind == "ACTIVITY_TASK_SCHEDULED":
            activity_type = attributes(attributes(event, "activityTaskScheduledEventAttributes"), "activityType")
            activity_name[str(event["eventId"])] = str(activity_type["name"])
        elif kind == "ACTIVITY_TASK_STARTED":
            details = attributes(event, "activityTaskStartedEventAttributes")
            activity_start[str(details["scheduledEventId"])] = (str(details["identity"]), int(str(details["attempt"])))
        elif kind in ACTIVITY_OUTCOMES:
            outcome, key = ACTIVITY_OUTCOMES[kind]
            scheduled_id = str(attributes(event, key)["scheduledEventId"])
            identity, attempt = activity_start.get(scheduled_id, (None, None))
            activities.append(ActivityFact(activity_name[scheduled_id], outcome, identity, attempt))
    return IdentityFacts(
        first_identity=first_started[0] if first_started else None,
        wt1=wt1[0] if wt1 else None,
        wt1_identity=wt1[1] if wt1 else None,
        wt1_attempt=wt1[2] if wt1 else None,
        timeout_identities=tuple(timeouts),
        activities=tuple(activities),
    )


def format_identity_line(line: str, facts: IdentityFacts) -> str:
    """Append the identity entries to a history's default gap line.

    Args:
        line: The line `format_history` built; it is kept whole at the start.
        facts: The same history reduced by `identity_facts`.

    Returns:
        The line plus, each after " | ": "wt1 on <first identity>", then "-> <identity>" only when the Workflow
        Task that completed WT1 ran on a different identity, then "attempt N" (always printed when WT1 exists),
        one entry per Workflow Task timeout, and one entry per Activity.
    """
    entries: list[str] = []

    # The first Workflow Task, and the retry that completed WT1 when it ran elsewhere.
    if facts.first_identity:
        wt_entry = f"wt1 on {facts.first_identity}"
        if facts.wt1_identity and facts.wt1_identity != facts.first_identity:
            wt_entry += f" -> {facts.wt1_identity}"
        if facts.wt1_attempt is not None:
            wt_entry += f" attempt {facts.wt1_attempt}"
        entries.append(wt_entry)

    # Every timeout on any Workflow Task, then every Activity with its outcome marked when it did not complete.
    entries += [f"wt timeout on {identity}" for identity in facts.timeout_identities]
    for activity in facts.activities:
        marker = "" if activity.outcome == "completed" else f" {activity.outcome.upper()}"
        where = f"on {activity.identity} attempt {activity.attempt}" if activity.identity else "on no Worker"
        entries.append(f"{activity.name}{marker} {where}")
    return " | ".join([line, *entries])


def summarize_identities(all_facts: Iterable[IdentityFacts]) -> list[str]:
    """Fold per-history facts into one summary line per identity.

    Args:
        all_facts: The facts of every history read.

    Returns:
        One line per identity, sorted by identity: the first Workflow Tasks it started, the Workflow Task
        timeouts it holds, the Activities that failed (timed out or failed) on it, and the largest WT1 among
        the histories whose first Workflow Task it started.
    """
    first_tasks: dict[str, int] = {}
    timeout_counts: dict[str, int] = {}
    failed_counts: dict[str, int] = {}
    largest_wt1: dict[str, timedelta] = {}
    for facts in all_facts:
        if facts.first_identity:
            first_tasks[facts.first_identity] = first_tasks.get(facts.first_identity, 0) + 1
            if facts.wt1 is not None:
                largest_wt1[facts.first_identity] = max(facts.wt1, largest_wt1.get(facts.first_identity, facts.wt1))
        for identity in facts.timeout_identities:
            timeout_counts[identity] = timeout_counts.get(identity, 0) + 1
        for activity in facts.activities:
            if activity.identity and activity.outcome != "completed":
                failed_counts[activity.identity] = failed_counts.get(activity.identity, 0) + 1
    identities = sorted({*first_tasks, *timeout_counts, *failed_counts})
    return [
        f"{identity}: first Workflow Tasks {first_tasks.get(identity, 0)}"
        f" | Workflow Task timeouts {timeout_counts.get(identity, 0)}"
        f" | Activities failed {failed_counts.get(identity, 0)}"
        f" | largest WT1 {span_ms(largest_wt1[identity]) if identity in largest_wt1 else 'none'}"
        for identity in identities
    ]


def receipt_ids(limit: str, runner: Runner) -> list[str]:
    """List the newest `limit` Workflows and keep the OrderReceiptWorkflow IDs."""
    listing = json.loads(runner(["workflow", "list", "--limit", limit, "--output", "json"]))
    return [
        str(entry["execution"]["workflowId"]) for entry in listing if entry["type"]["name"] == "OrderReceiptWorkflow"
    ]


def main(argv: Sequence[str] | None = None, runner: Runner = run_temporal, emit: Callable[[str], None] = print) -> int:
    """Print one gap line per receipt Workflow named by ID or found by `--limit`.

    With `--by-identity`, each line gains the Worker identities and the per-identity summary follows the lines;
    with `--summary` as well, only the summary is printed.

    Args:
        argv: The command-line arguments; None reads `sys.argv`.
        runner: Runs a Temporal CLI call and returns its standard output.
        emit: Receives each output line.

    Returns:
        The process exit code, always 0; argparse exits on a bad flag combination.
    """
    parser = argparse.ArgumentParser(description="Print WT1 and Activity gaps for OrderReceiptWorkflow runs.")
    parser.add_argument("workflow_ids", nargs="*", help="Workflow IDs to inspect")
    parser.add_argument("--limit", help="inspect the OrderReceiptWorkflow runs among the newest N Workflows")
    parser.add_argument(
        "--by-identity",
        action="store_true",
        help="add the Worker identity on each Started event to every line, then one summary line per identity",
    )
    parser.add_argument("--summary", action="store_true", help="with --by-identity, print only the summary lines")
    args = parser.parse_args(argv)
    if args.summary and not args.by_identity:
        parser.error("--summary is valid only with --by-identity")
    workflow_ids = list(args.workflow_ids)
    if args.limit:
        workflow_ids += receipt_ids(args.limit, runner)
    all_facts: list[IdentityFacts] = []
    for workflow_id in workflow_ids:
        history = json.loads(runner(["workflow", "show", "-w", workflow_id, "--output", "json"]))
        line = format_history(workflow_id, history["events"])
        if args.by_identity:
            facts = identity_facts(history["events"])
            all_facts.append(facts)
            line = format_identity_line(line, facts)
        if not args.summary:
            emit(line)
    for summary_line in summarize_identities(all_facts):
        emit(summary_line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
