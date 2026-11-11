"""ABOUTME: Tests for the flood starter: its flags, its freeze gate, and the order of the flood's steps.
ABOUTME: No test touches a Temporal server; the flow runs against a recording fake client and a fake lock.

Every sleep is replaced by one that records its length and yields once, so the flow runs in
milliseconds. The fake lock records when the flow enters it, arms it, and leaves it, so the tests can
check that the healthy flood never takes the lock and the bad flood arms it right after the bad run.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self, cast

import pytest
import starter
from flood import flood_due_times, planned_duration
from shared import GeoEnrichmentInput
from starter import (
    FREEZE_GATE_ACTIVITY,
    GATE_POLL_INTERVAL_SECONDS,
    GATE_TIMEOUT_SECONDS,
    ROLLUP_HEAD_START_SECONDS,
    build_parser,
    run_flood,
    wait_for_activity_started,
)
from temporalio.client import PendingActivityState, WorkflowFailureError
from temporalio.exceptions import ApplicationError

if TYPE_CHECKING:
    from pathlib import Path
    from types import TracebackType

    from temporalio.client import Client, WorkflowHandle

FAKE_DATABASE_NAME: str = "location-cache-test.sqlite3"
"""The file name the fake lock reports, inside whatever directory the starter hands it."""

_PendingActivity = tuple[str, PendingActivityState]
"""A pending activity describe() reports: its registered name and its state."""

# The names are literals on purpose: they pin the activity the gate waits on to the one plan.md names.
_GET_IP_STARTED: _PendingActivity = ("get_ip", PendingActivityState.STARTED)
_GET_LOCATION_SCHEDULED: _PendingActivity = ("get_location", PendingActivityState.SCHEDULED)
_GET_LOCATION_STARTED: _PendingActivity = ("get_location", PendingActivityState.STARTED)


@dataclass(frozen=True)
class _FakeActivityType:
    """The one field of a server-side ActivityType the gate reads."""

    name: str


@dataclass(frozen=True)
class _FakePendingActivity:
    """The two fields of a server-side PendingActivityInfo the gate reads."""

    activity_type: _FakeActivityType
    state: int


@dataclass(frozen=True)
class _FakeRawDescription:
    """The one field of a DescribeWorkflowExecutionResponse the gate reads."""

    pending_activities: list[_FakePendingActivity]


@dataclass(frozen=True)
class _FakeDescription:
    """A WorkflowExecutionDescription stand-in carrying only the raw description."""

    raw_description: _FakeRawDescription


@dataclass
class _FakeHandle:
    """A started-workflow stand-in whose result is immediate and whose describe() reports fixed activities.

    Attributes:
        id: The workflow id the run was started under.
        events: The shared event log; every describe() call records "describe".
        pending: The pending activities every describe() call reports; empty for none.
        failure: When set, result() raises it, as a failed workflow would.
    """

    id: str
    events: list[str]
    pending: list[_PendingActivity] = field(default_factory=lambda: [_GET_LOCATION_STARTED])
    failure: WorkflowFailureError | None = None

    async def result(self) -> str:
        """Return a fixed result, or raise the scripted failure."""
        if self.failure is not None:
            raise self.failure
        return "done"

    async def describe(self) -> _FakeDescription:
        """Record the call and report the scripted pending activities."""
        self.events.append("describe")
        pending = [_FakePendingActivity(_FakeActivityType(name), int(state)) for name, state in self.pending]
        return _FakeDescription(_FakeRawDescription(pending))


def _chained_failure(outer_message: str, inner_message: str) -> WorkflowFailureError:
    """Build a workflow failure whose cause has a cause of its own, as an activity timeout does."""
    outer = ApplicationError(outer_message)
    outer.__cause__ = ApplicationError(inner_message)
    return WorkflowFailureError(cause=outer)


@dataclass
class _FakeClient:
    """A Temporal client stand-in that records each start, in order.

    Attributes:
        events: The shared event log. A receipt records "receipt", a rollup "rollup", and a geo run
            "geo:<location_cache_path>".
        pending: Passed to every geo handle; see _FakeHandle.
        failing_receipts: How many of the first receipts fail, each with the same chained failure.
        receipts_started: How many receipts have been started so far.
    """

    events: list[str]
    pending: list[_PendingActivity] = field(default_factory=lambda: [_GET_LOCATION_STARTED])
    failing_receipts: int = 0
    receipts_started: int = 0

    async def start_workflow(self, _run: object, workflow_input: object, *, id: str, task_queue: str) -> _FakeHandle:
        """Record the start and return a handle; receipts past failing_receipts complete."""
        kind = id.split("-", 1)[0]
        if isinstance(workflow_input, GeoEnrichmentInput):
            self.events.append(f"geo:{workflow_input.location_cache_path}")
            return _FakeHandle(id=id, events=self.events, pending=self.pending)
        self.events.append(kind)
        failure = None
        if kind == "receipt":
            self.receipts_started += 1
            if self.receipts_started <= self.failing_receipts:
                failure = _chained_failure("activity ScheduleToClose timeout", "activity StartToClose timeout")
        return _FakeHandle(id=id, events=self.events, failure=failure)


@dataclass
class _FakeCacheLock:
    """A CacheLock stand-in that records entering, arming, and leaving, and holds nothing.

    Attributes:
        database_path: The path the bad runs are pointed at.
        events: The shared event log.
        directory_existed: Whether the directory the starter handed in existed when the lock was entered.
    """

    database_path: Path
    events: list[str]
    directory_existed: bool = False

    def arm(self) -> None:
        """Record the arm."""
        self.events.append("lock:arm")

    def __enter__(self) -> Self:
        """Record the entry and whether the database's directory exists."""
        self.events.append("lock:enter")
        self.directory_existed = self.database_path.parent.is_dir()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Record the exit."""
        self.events.append("lock:exit")


@dataclass
class _LockRecorder:
    """Replaces hold_cache_lock, keeping each call's arguments and the lock it returned."""

    events: list[str]
    calls: list[tuple[float, Path]] = field(default_factory=list)
    locks: list[_FakeCacheLock] = field(default_factory=list)

    def __call__(self, delay_seconds: float, directory: Path) -> _FakeCacheLock:
        """Record the call and return a fake lock whose database sits in directory."""
        self.calls.append((delay_seconds, directory))
        lock = _FakeCacheLock(database_path=directory / FAKE_DATABASE_NAME, events=self.events)
        self.locks.append(lock)
        return lock


_REAL_SLEEP = asyncio.sleep
"""asyncio.sleep before any test patches it, for fakes that still need to yield to the loop."""


@dataclass
class _VirtualClock:
    """A monotonic clock that only the patched sleep moves, with one scripted late wake.

    Attributes:
        now: The current virtual time, in seconds.
        late_wake_at: The first sleep due to wake at or after this time wakes late.
        late_by: How many seconds late that one sleep wakes.
        sleeps: The length of every sleep requested, in order.
        late_wake_index: The position in sleeps of the sleep that woke late, once it has.
    """

    late_wake_at: float
    late_by: float
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)
    late_wake_index: int | None = None

    def monotonic(self) -> float:
        """Read the virtual time."""
        return self.now

    async def sleep(self, seconds: float) -> None:
        """Record the sleep, move the clock to its wake time (late once), and yield once."""
        self.sleeps.append(seconds)
        wake_at = self.now + seconds
        if self.late_wake_index is None and wake_at >= self.late_wake_at:
            self.late_wake_index = len(self.sleeps) - 1
            wake_at += self.late_by
        self.now = wake_at
        await _REAL_SLEEP(0)


def _install_clock(monkeypatch: pytest.MonkeyPatch, clock: _VirtualClock) -> None:
    """Point the starter's monotonic and asyncio.sleep at the virtual clock."""
    monkeypatch.setattr(starter, "monotonic", clock.monotonic)
    monkeypatch.setattr(asyncio, "sleep", clock.sleep)


@pytest.fixture
def events() -> list[str]:
    """The shared event log for one test."""
    return []


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> list[float]:
    """Replace asyncio.sleep with one that records its length and yields once, so nothing waits."""
    real_sleep = asyncio.sleep
    sleeps: list[float] = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        events.append(f"sleep:{seconds}")
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    return sleeps


@pytest.fixture
def lock_recorder(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> _LockRecorder:
    """Replace the starter's hold_cache_lock with a recorder that hands back fake locks."""
    recorder = _LockRecorder(events)
    monkeypatch.setattr(starter, "hold_cache_lock", recorder)
    return recorder


def test_flag_defaults() -> None:
    """With no flags, the parser applies the default flood: 10 per second, 10/30/10 seconds, one rollup, one bad run."""
    args = build_parser().parse_args([])

    assert (args.rate, args.lead, args.block_seconds, args.tail) == (10.0, 10.0, 30.0, 10.0)
    assert (args.rollups, args.bad) == (1, 1)


def test_bad_zero_selects_the_healthy_flood() -> None:
    """--bad 0 parses to zero bad runs."""
    assert build_parser().parse_args(["--bad", "0"]).bad == 0


@pytest.mark.parametrize("argv", [["--rate", "0"], ["--rate", "-1"], ["--bad", "-1"]])
def test_a_rate_that_is_not_positive_and_a_negative_bad_count_are_rejected(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """The parser exits with a usage error instead of starting a flood that cannot run."""
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(argv)

    assert exit_info.value.code == 2
    assert "invalid" in capsys.readouterr().err


async def test_the_gate_returns_true_once_the_activity_reports_started(recorded_sleeps: list[float]) -> None:
    """A get_location reported STARTED on the first describe() opens the gate at once."""
    handle = _FakeHandle(id="geo-1", events=[], pending=[_GET_IP_STARTED, _GET_LOCATION_STARTED])

    started = await wait_for_activity_started(cast("WorkflowHandle[object, object]", handle), FREEZE_GATE_ACTIVITY, 5.0)

    assert started is True
    assert recorded_sleeps == []


async def test_the_gate_keeps_polling_a_scheduled_activity_and_gives_up_at_the_timeout(
    recorded_sleeps: list[float],
) -> None:
    """A get_location that stays SCHEDULED is polled for the whole budget, then the gate returns False."""
    events: list[str] = []
    handle = _FakeHandle(id="geo-1", events=events, pending=[_GET_LOCATION_SCHEDULED])

    started = await wait_for_activity_started(cast("WorkflowHandle[object, object]", handle), FREEZE_GATE_ACTIVITY, 5.0)

    assert started is False
    assert events.count("describe") == round(5.0 / GATE_POLL_INTERVAL_SECONDS)
    assert set(recorded_sleeps) == {GATE_POLL_INTERVAL_SECONDS}


async def test_the_gate_returns_false_when_nothing_is_pending(recorded_sleeps: list[float]) -> None:
    """With no pending activity at all, the gate never opens."""
    handle = _FakeHandle(id="geo-1", events=[], pending=[])

    started = await wait_for_activity_started(cast("WorkflowHandle[object, object]", handle), FREEZE_GATE_ACTIVITY, 1.0)

    assert started is False


@pytest.mark.parametrize(
    "pending",
    [[_GET_IP_STARTED], [_GET_IP_STARTED, _GET_LOCATION_SCHEDULED]],
    ids=["get_location-absent", "get_location-scheduled"],
)
async def test_a_started_get_ip_never_opens_the_gate(
    pending: list[_PendingActivity], recorded_sleeps: list[float]
) -> None:
    """get_ip reports STARTED before get_location does; only get_location STARTED confirms the freeze."""
    events: list[str] = []
    handle = _FakeHandle(id="geo-1", events=events, pending=pending)

    started = await wait_for_activity_started(cast("WorkflowHandle[object, object]", handle), FREEZE_GATE_ACTIVITY, 5.0)

    assert started is False
    assert events.count("describe") == round(5.0 / GATE_POLL_INTERVAL_SECONDS)


async def test_the_healthy_flood_takes_no_lock_and_submits_exactly_the_planned_receipts(
    events: list[str],
    recorded_sleeps: list[float],
    lock_recorder: _LockRecorder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bad 0 submits the planned stream and the rollup, never calls hold_cache_lock, and starts no geo run."""
    args = build_parser().parse_args(["--bad", "0", "--lead", "1", "--block-seconds", "1", "--tail", "1"])
    planned = len(flood_due_times(args.rate, planned_duration(args.lead, args.block_seconds, args.tail)))

    await run_flood(cast("Client", _FakeClient(events)), args)

    assert lock_recorder.calls == []
    assert events.count("receipt") == planned
    assert events.count("rollup") == 1
    assert not any(event.startswith(("geo", "lock", "describe")) for event in events)
    output = capsys.readouterr().out
    assert f"receipts submitted={planned} failed=0" in output
    assert "relative to the end of the lead" in output


async def test_the_bad_flood_submits_the_rollup_then_the_bad_run_then_arms_the_lock_and_gates(
    events: list[str],
    recorded_sleeps: list[float],
    lock_recorder: _LockRecorder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--bad 1: rollup, a 1-second head start, the bad run on the lock's database, arm(), then the gate."""
    args = build_parser().parse_args(["--lead", "1", "--block-seconds", "2", "--tail", "1"])

    await run_flood(cast("Client", _FakeClient(events)), args)

    # The lock was created for the block length in a directory that existed, and is cleaned up after.
    [(delay_seconds, directory)] = lock_recorder.calls
    [lock] = lock_recorder.locks
    assert delay_seconds == 2.0
    assert lock.directory_existed
    assert not directory.exists()

    # Ignoring the receipt stream and its sleeps, the flow runs its steps in order.
    steps = [event for event in events if event != "receipt" and not event.startswith("sleep:")]
    bad_run = f"geo:{lock.database_path}"
    assert steps[:5] == ["lock:enter", "rollup", bad_run, "lock:arm", "describe"]
    assert steps[-1] == "lock:exit"
    head_start = events.index("rollup") + events[events.index("rollup") : events.index(bad_run)].index(
        f"sleep:{ROLLUP_HEAD_START_SECONDS}"
    )
    assert events.index("rollup") < head_start < events.index(bad_run)
    assert "relative to the confirmed freeze" in capsys.readouterr().out


async def test_an_unconfirmed_freeze_says_so_and_the_flood_still_finishes(
    events: list[str],
    recorded_sleeps: list[float],
    lock_recorder: _LockRecorder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the gate times out, the starter prints one line saying so and times the timeline from the bad run."""
    args = build_parser().parse_args(["--lead", "1", "--block-seconds", "1", "--tail", "1"])

    await run_flood(cast("Client", _FakeClient(events, pending=[_GET_IP_STARTED, _GET_LOCATION_SCHEDULED])), args)

    output = capsys.readouterr().out
    assert events.count("describe") == round(GATE_TIMEOUT_SECONDS / GATE_POLL_INTERVAL_SECONDS)
    assert "freeze not confirmed" in output
    assert "relative to the bad run's submit time" in output
    assert events[-1] == "lock:exit"


async def test_a_failed_receipt_is_counted_and_never_aborts_the_flood(
    events: list[str],
    recorded_sleeps: list[float],
    lock_recorder: _LockRecorder,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two failed receipts land in the totals with the whole cause chain, and every planned receipt still runs."""
    args = build_parser().parse_args(["--bad", "0", "--lead", "1", "--block-seconds", "0", "--tail", "1"])
    planned = len(flood_due_times(args.rate, planned_duration(args.lead, args.block_seconds, args.tail)))

    await run_flood(cast("Client", _FakeClient(events, failing_receipts=2)), args)

    output = capsys.readouterr().out
    assert events.count("receipt") == planned
    assert f"receipts submitted={planned} failed=2" in output
    assert "first failure: activity ScheduleToClose timeout caused by activity StartToClose timeout" in output
    assert "receipt-" not in output


# With --lead 0 the flow's only real wait is the producer's, so the virtual clock moves on the producer's sleeps.
_SLIP_FLOOD_ARGV: list[str] = ["--bad", "0", "--lead", "0", "--block-seconds", "1", "--tail", "1"]
"""A healthy flood of 20 receipts at 10 per second, 0.1 seconds apart."""


async def test_a_wake_several_spacings_late_shifts_the_plan_and_prints_the_note_before_the_summary(
    events: list[str],
    lock_recorder: _LockRecorder,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A wake 0.35 s late is not caught up with a burst: the next sleep is one spacing, and the slip is reported."""
    clock = _VirtualClock(late_wake_at=0.5, late_by=0.35)
    _install_clock(monkeypatch, clock)
    args = build_parser().parse_args(_SLIP_FLOOD_ARGV)
    spacing = 1 / args.rate
    planned = len(flood_due_times(args.rate, planned_duration(args.lead, args.block_seconds, args.tail)))

    await run_flood(cast("Client", _FakeClient(events)), args)

    assert clock.late_wake_index is not None
    later_sleeps = clock.sleeps[clock.late_wake_index + 1 :]
    assert later_sleeps
    assert later_sleeps == [pytest.approx(spacing)] * len(later_sleeps)
    assert events.count("receipt") == planned
    output = capsys.readouterr().out
    note = "note: the producer fell 0.35s behind its plan; later receipts kept their spacing"
    assert note in output
    assert output.index(note) < output.index(f"receipts submitted={planned} failed=0")


async def test_a_wake_late_by_less_than_one_spacing_prints_no_note(
    events: list[str],
    lock_recorder: _LockRecorder,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A wake 0.05 s late at 10 per second is timer jitter: the plan does not shift and no note is printed."""
    clock = _VirtualClock(late_wake_at=0.5, late_by=0.05)
    _install_clock(monkeypatch, clock)
    args = build_parser().parse_args(_SLIP_FLOOD_ARGV)
    planned = len(flood_due_times(args.rate, planned_duration(args.lead, args.block_seconds, args.tail)))

    await run_flood(cast("Client", _FakeClient(events)), args)

    assert clock.late_wake_index is not None
    assert clock.sleeps[clock.late_wake_index + 1] == pytest.approx(0.05)
    assert events.count("receipt") == planned
    output = capsys.readouterr().out
    assert "note:" not in output
    assert f"receipts submitted={planned} failed=0" in output
