"""ABOUTME: CLI-contract tests for the starter's argument parser, input helpers, and metrics parser.
ABOUTME: No test touches a Temporal server; submission order runs against a recording fake client.

These tests pin the flag names, defaults, and choices, prove that the count flags fan out into the
right workflow inputs, and check that the metrics parser reads the ActivityWorker slot gauge rather
than the LocalActivityWorker line.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest
from temporalio import activity
from temporalio.client import PendingActivityState
from temporalio.service import RPCError, RPCStatusCode

from temporal_async_debug import starter
from temporal_async_debug.activities import get_ip, get_location
from temporal_async_debug.shared import (
    VALID_MODES,
    GeoEnrichmentInput,
    OrderReceiptInput,
    PriceQuoteInput,
    SalesRollupInput,
)
from temporal_async_debug.starter import (
    FREEZE_FALLBACK_DELAY_SECONDS,
    FREEZE_GATE_ACTIVITY,
    FREEZE_LOCK_GUARD_SECONDS,
    FREEZE_MODES,
    LOCK_POLL_DISPATCH_MARGIN_SECONDS,
    LOCK_POLL_INTERVAL_SECONDS,
    LOCK_POLL_MIN_TIMEOUT_SECONDS,
    SATURATION_MODES,
    Fleet,
    bad_geo_inputs_from_args,
    build_parser,
    fleet_from_args,
    healthy_geo_inputs_from_args,
    lock_poll_timeout_seconds,
    parse_activity_slots_available,
    quote_inputs_from_args,
    receipt_inputs_from_args,
    rollup_inputs_from_args,
    run_main,
    select_scenario,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from temporalio.client import Client

_LABELS = 'namespace="default",service_name="temporal-core-sdk",task_queue="async-debug-task-queue"'
"""The label set the real worker emits, shared by the metrics-parsing fixtures below."""


def _metrics_page(activity_free: int) -> str:
    """Build a metrics page with the given ActivityWorker free-slot count.

    The LocalActivityWorker line comes first on purpose: its label contains "ActivityWorker" as a
    substring, so a loosened pattern that matches it would return 100 here and fail the test.
    """
    return (
        "# HELP temporal_worker_task_slots_available Current number of available slots per task type\n"
        "# TYPE temporal_worker_task_slots_available gauge\n"
        f'temporal_worker_task_slots_available{{{_LABELS},worker_type="LocalActivityWorker"}} 100\n'
        f'temporal_worker_task_slots_available{{{_LABELS},worker_type="ActivityWorker"}} {activity_free}\n'
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
    assert args.rollups == 0
    assert args.quotes == 0


def test_mode_rejects_invalid_value() -> None:
    """--mode is restricted to shared.VALID_MODES; anything else exits via argparse."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--mode", "sideways"])


@pytest.mark.parametrize("mode", VALID_MODES)
def test_mode_accepts_known_values(mode: str) -> None:
    """Every mode in shared.VALID_MODES parses without error, sourced from the same constant."""
    assert build_parser().parse_args(["--mode", mode]).mode == mode


def test_numeric_flags_parse_to_their_types() -> None:
    """--block-seconds parses as float; --bad, --geo, --receipts, --rollups, and --quotes parse as int."""
    args = build_parser().parse_args(
        [
            "--block-seconds",
            "1.5",
            "--bad",
            "2",
            "--geo",
            "4",
            "--receipts",
            "7",
            "--rollups",
            "3",
            "--quotes",
            "1",
        ]
    )

    assert isinstance(args.block_seconds, float)
    assert args.block_seconds == 1.5
    assert args.bad == 2
    assert args.geo == 4
    assert args.receipts == 7
    assert args.rollups == 3
    assert args.quotes == 1


def test_full_flag_set_parses_to_expected_values() -> None:
    """The full flag set from a saturation scenario parses to exactly the typed values given."""
    args = build_parser().parse_args(
        [
            "--mode",
            "stuck_no_heartbeat",
            "--block-seconds",
            "30",
            "--bad",
            "1",
            "--geo",
            "1",
            "--rollups",
            "2",
            "--receipts",
            "2",
            "--quotes",
            "1",
        ]
    )

    assert args.mode == "stuck_no_heartbeat"
    assert args.block_seconds == 30.0
    assert args.bad == 1
    assert args.geo == 1
    assert args.rollups == 2
    assert args.receipts == 2
    assert args.quotes == 1


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


def test_rollup_inputs_have_distinct_periods() -> None:
    """--rollups 3 yields three SalesRollupInput values with three distinct periods."""
    args = build_parser().parse_args(["--rollups", "3"])

    rollup_inputs = rollup_inputs_from_args(args)

    assert len(rollup_inputs) == 3
    assert all(isinstance(rollup_input, SalesRollupInput) for rollup_input in rollup_inputs)
    periods = [rollup_input.period for rollup_input in rollup_inputs]
    assert len(set(periods)) == 3


def test_quote_inputs_have_distinct_skus() -> None:
    """--quotes 2 yields two PriceQuoteInput values with two distinct skus."""
    args = build_parser().parse_args(["--quotes", "2"])

    quote_inputs = quote_inputs_from_args(args)

    assert len(quote_inputs) == 2
    assert all(isinstance(quote_input, PriceQuoteInput) for quote_input in quote_inputs)
    skus = [quote_input.sku for quote_input in quote_inputs]
    assert len(set(skus)) == 2


def test_counts_default_to_empty_fleets() -> None:
    """The defaults produce no workflows of any kind."""
    args = build_parser().parse_args([])

    assert bad_geo_inputs_from_args(args) == []
    assert healthy_geo_inputs_from_args(args) == []
    assert receipt_inputs_from_args(args) == []
    assert rollup_inputs_from_args(args) == []
    assert quote_inputs_from_args(args) == []


@pytest.mark.parametrize("activity_free", [0, 1, 2])
def test_parse_activity_slots_reads_the_activity_worker_gauge(activity_free: int) -> None:
    """The parser returns the ActivityWorker free-slot value, not the LocalActivityWorker one."""
    assert parse_activity_slots_available(_metrics_page(activity_free)) == activity_free


def test_parse_activity_slots_returns_none_when_absent() -> None:
    """A metrics page without the activity slot gauge yields None, not a crash or a wrong reading."""
    assert parse_activity_slots_available("# nothing relevant here\n") is None


def test_mode_families_partition_the_valid_modes() -> None:
    """Every mode belongs to exactly one family, so no mode falls through to the unordered path."""
    assert set(FREEZE_MODES) | set(SATURATION_MODES) == set(VALID_MODES)
    assert set(FREEZE_MODES).isdisjoint(SATURATION_MODES)


def test_fleet_from_args_fans_every_count_flag_into_the_fleet() -> None:
    """fleet_from_args carries every bystander kind, so no scenario can lose a flag on the way in."""
    args = build_parser().parse_args(
        ["--mode", "cpu", "--block-seconds", "30", "--bad", "1", "--geo", "2", "--receipts", "3"]
        + ["--rollups", "4", "--quotes", "5"]
    )

    fleet = fleet_from_args(args)

    assert len(fleet.bad_geo) == 1
    assert all(bad_input.mode == "cpu" for bad_input in fleet.bad_geo)
    assert len(fleet.healthy_geo) == 2
    assert len(fleet.receipts) == 3
    assert len(fleet.rollups) == 4
    assert len(fleet.quotes) == 5


@pytest.mark.parametrize(
    ("flags", "expected_scenario"),
    [
        (["--mode", "block", "--bad", "1", "--receipts", "2"], "freeze"),
        (["--mode", "cpu", "--bad", "1", "--quotes", "1"], "freeze"),
        (["--mode", "cpu", "--bad", "1", "--geo", "1"], "freeze"),
        (["--mode", "slow", "--bad", "2", "--geo", "1"], "saturation"),
        (["--mode", "stuck_no_heartbeat", "--bad", "1", "--geo", "1"], "saturation"),
        (["--mode", "slow_heartbeat", "--bad", "2", "--rollups", "1"], "saturation"),
        (["--mode", "slow", "--bad", "2"], "concurrent"),
        (["--mode", "block", "--geo", "2", "--receipts", "3"], "concurrent"),
    ],
)
def test_select_scenario_routes_each_bystander_kind_to_its_mode_family(
    flags: list[str],
    expected_scenario: str,
) -> None:
    """Any bystander kind triggers the mode family's ordering; no bad runs or no bystanders do not."""
    args = build_parser().parse_args([*flags, "--block-seconds", "30"])

    assert select_scenario(args.mode, args.block_seconds, fleet_from_args(args)) == expected_scenario


def test_select_scenario_runs_concurrently_when_the_bad_runs_have_no_delay() -> None:
    """A bad run with zero block_seconds is healthy, so there is nothing to sequence around."""
    args = build_parser().parse_args(["--mode", "block", "--bad", "1", "--receipts", "2"])

    assert select_scenario(args.mode, args.block_seconds, fleet_from_args(args)) == "concurrent"


@dataclass(frozen=True)
class _FakeActivityType:
    """The one field of a server-side ActivityType the starter reads."""

    name: str


@dataclass(frozen=True)
class _FakePendingActivity:
    """The two fields of a server-side PendingActivityInfo the starter reads."""

    activity_type: _FakeActivityType
    state: int


@dataclass(frozen=True)
class _FakeRawDescription:
    """The one field of a DescribeWorkflowExecutionResponse the starter reads."""

    pending_activities: list[_FakePendingActivity]


@dataclass(frozen=True)
class _FakeDescription:
    """A WorkflowExecutionDescription stand-in carrying only the raw description."""

    raw_description: _FakeRawDescription


_GET_IP_STARTED = (get_ip.__name__, PendingActivityState.STARTED)
_GET_LOCATION_SCHEDULED = (get_location.__name__, PendingActivityState.SCHEDULED)
_GET_LOCATION_STARTED = (get_location.__name__, PendingActivityState.STARTED)

_PendingScript = list[tuple[str, PendingActivityState]]
"""The pending activity each describe() call reports, in order; the last entry repeats once exhausted."""


@dataclass
class _FakeHandle:
    """A started-workflow stand-in whose result is immediate and whose describe() is scripted.

    Attributes:
        id: The workflow id the run was started under.
        label: The label the run was recorded under; every result() call records "result:<label>".
        events: The shared event log; every describe() call records "describe".
        describe_script: The (activity type, state) each describe() call reports, in order.
        describe_raises: When True, describe() raises an RPCError, as it would if the server failed.
    """

    id: str
    label: str
    events: list[str]
    describe_script: _PendingScript
    describe_raises: bool = False

    async def result(self) -> str:
        """Record the call and return a fixed result, as a completed workflow would."""
        self.events.append(f"result:{self.label}")
        return "done"

    async def describe(self) -> _FakeDescription:
        """Record the call and report the pending activity for this point in the script."""
        self.events.append("describe")
        if self.describe_raises:
            raise RPCError("server unavailable", RPCStatusCode.UNAVAILABLE, b"")
        activity_name, state = self.describe_script[0]
        if len(self.describe_script) > 1:
            self.describe_script = self.describe_script[1:]
        pending = _FakePendingActivity(activity_type=_FakeActivityType(name=activity_name), state=int(state))
        return _FakeDescription(_FakeRawDescription([pending]))


@dataclass
class _FakeClient:
    """A Temporal client stand-in that records each start as a label, in order.

    Attributes:
        events: Labels in the order the starter did things, shared with the slot-poll fakes.
        describe_script: Copied to every handle; see _FakeHandle. Defaults to get_location already STARTED.
        describe_raises: Passed to every handle; see _FakeHandle.
        labels_by_id: The label each started workflow id was recorded under.
    """

    events: list[str]
    describe_script: _PendingScript = field(default_factory=lambda: [_GET_LOCATION_STARTED])
    describe_raises: bool = False
    labels_by_id: dict[str, str] = field(default_factory=dict)

    async def start_workflow(self, _run: object, workflow_input: object, *, id: str, task_queue: str) -> _FakeHandle:
        """Record the start, labeling geo runs as bad or healthy by their delay."""
        label = id.split("-", 1)[0]
        if isinstance(workflow_input, GeoEnrichmentInput):
            label = "geo:bad" if workflow_input.block_seconds > 0 else "geo:healthy"
        self.events.append(label)
        self.labels_by_id[id] = label
        return _FakeHandle(
            id=id,
            label=label,
            events=self.events,
            describe_script=list(self.describe_script),
            describe_raises=self.describe_raises,
        )


def _submission_events(events: list[str]) -> list[str]:
    """Drop the trailing result() calls the final report makes, leaving what the starter did before it."""
    last_submission = max(index for index, event in enumerate(events) if not event.startswith("result:"))
    return events[: last_submission + 1]


def _install_slot_fakes(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    baseline_free: int | None,
    *,
    slots_reached: bool = True,
) -> None:
    """Replace the metrics reads and asyncio.sleep with fakes that record into events, so nothing sleeps.

    The baseline read returns baseline_free, the slot wait records its target and returns
    slots_reached (False drives the gauge wait's timeout path), and every sleep records its duration.
    """

    async def read_free_slots() -> int | None:
        return baseline_free

    async def wait_for_slots(target_free: int) -> bool:
        events.append(f"wait:{target_free}")
        return slots_reached

    async def record_sleep(seconds: float) -> None:
        events.append(f"sleep:{seconds}")

    monkeypatch.setattr(starter, "_read_free_activity_slots", read_free_slots)
    monkeypatch.setattr(starter, "wait_for_free_activity_slots", wait_for_slots)
    monkeypatch.setattr(asyncio, "sleep", record_sleep)


def _reported_labels(output: str, client: _FakeClient) -> list[str]:
    """Map each printed result line back to the label its workflow was started under."""
    return [client.labels_by_id[line.split()[1].rstrip(":")] for line in output.splitlines() if " " in line]


def _full_fleet(mode: str, bad_count: int) -> Fleet:
    """Build a fleet with one of every bystander kind and bad_count bad geo runs in mode."""
    args = build_parser().parse_args(
        ["--mode", mode, "--block-seconds", "30", "--bad", str(bad_count), "--geo", "1"]
        + ["--receipts", "1", "--rollups", "1", "--quotes", "1"]
    )
    return fleet_from_args(args)


def _instant_only_fleet() -> Fleet:
    """Build a freeze fleet with one bad run and only the instant bystanders, receipts and quotes."""
    args = build_parser().parse_args(
        ["--mode", "block", "--block-seconds", "30", "--bad", "1", "--receipts", "1", "--quotes", "1"]
    )
    return fleet_from_args(args)


def _healthy_geo_only_fleet() -> Fleet:
    """Build a freeze fleet with one bad run, one healthy geo run, and one receipt."""
    args = build_parser().parse_args(
        ["--mode", "block", "--block-seconds", "30", "--bad", "1", "--geo", "1", "--receipts", "1"]
    )
    return fleet_from_args(args)


def test_freeze_gate_activity_is_the_name_the_sdk_registers_for_get_location() -> None:
    """The gate matches pending activities by the registered name, so renaming get_location (or giving
    its activity.defn an explicit name) cannot silently leave the gate waiting on a name nothing reports."""
    definition = activity._Definition.must_from_callable(get_location)  # noqa: SLF001

    assert definition.name == FREEZE_GATE_ACTIVITY


@pytest.mark.parametrize(
    ("block_seconds", "expected_timeout"),
    [
        (0.0, LOCK_POLL_MIN_TIMEOUT_SECONDS),
        (5.0, LOCK_POLL_MIN_TIMEOUT_SECONDS),
        (30.0, 30.0 + LOCK_POLL_DISPATCH_MARGIN_SECONDS),
        (120.0, 120.0 + LOCK_POLL_DISPATCH_MARGIN_SECONDS),
    ],
)
def test_lock_poll_timeout_covers_the_first_freeze_with_a_floor(block_seconds: float, expected_timeout: float) -> None:
    """The gate waits through the whole first freeze plus dispatch, and never less than the floor."""
    assert LOCK_POLL_MIN_TIMEOUT_SECONDS >= 20.0
    assert LOCK_POLL_DISPATCH_MARGIN_SECONDS >= 10.0
    assert lock_poll_timeout_seconds(block_seconds) == expected_timeout


async def test_freeze_scenario_releases_instant_bystanders_only_once_get_location_starts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rollups and healthy geo go first, the healthy geo finishes before the freeze lands, and receipts
    and quotes wait until the bad run's second activity, get_location, reports STARTED plus the guard.
    A STARTED get_ip, or a get_location still SCHEDULED, must not release them early."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=2)
    client = _FakeClient(
        events,
        describe_script=[_GET_IP_STARTED, _GET_IP_STARTED, _GET_LOCATION_SCHEDULED, _GET_LOCATION_STARTED],
    )

    await starter._submit_freeze_scenario(cast("Client", client), _full_fleet("block", bad_count=1))

    poll = f"sleep:{LOCK_POLL_INTERVAL_SECONDS}"
    assert _submission_events(events) == [
        "rollup",
        "geo:healthy",
        "wait:1",
        "result:geo:healthy",
        "geo:bad",
        *["describe", poll] * 3,
        "describe",
        f"sleep:{FREEZE_LOCK_GUARD_SECONDS}",
        "receipt",
        "quote",
    ]
    assert _reported_labels(capsys.readouterr().out, client) == [
        "rollup",
        "geo:healthy",
        "receipt",
        "quote",
        "geo:bad",
    ]


async def test_freeze_scenario_with_only_instant_bystanders_gates_on_started_without_a_gauge_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no rollups or healthy geo, only the bad activity can hold a slot, so the gate must not
    wait for the gauge to read zero free; the STARTED report alone releases the receipts and quotes."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=2)

    await starter._submit_freeze_scenario(cast("Client", _FakeClient(events)), _instant_only_fleet())

    assert _submission_events(events) == [
        "geo:bad",
        "describe",
        f"sleep:{FREEZE_LOCK_GUARD_SECONDS}",
        "receipt",
        "quote",
    ]


async def test_freeze_scenario_warns_with_the_consequence_when_get_location_never_starts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If get_location never reports STARTED (here get_ip stays STARTED forever), the poll spends its
    block_seconds-scaled budget, warns what that means for the run, and still sleeps the guard."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=2)
    client = _FakeClient(events, describe_script=[_GET_IP_STARTED])

    await starter._submit_freeze_scenario(cast("Client", client), _full_fleet("block", bad_count=1))

    timeout = lock_poll_timeout_seconds(30.0)
    poll_events = events[events.index("geo:bad") + 1 : events.index(f"sleep:{FREEZE_LOCK_GUARD_SECONDS}")]
    assert poll_events.count("describe") == round(timeout / LOCK_POLL_INTERVAL_SECONDS)
    assert set(poll_events) == {"describe", f"sleep:{LOCK_POLL_INTERVAL_SECONDS}"}
    assert _submission_events(events)[-3:] == [f"sleep:{FREEZE_LOCK_GUARD_SECONDS}", "receipt", "quote"]
    assert (
        f"warning: {FREEZE_GATE_ACTIVITY} never reported STARTED within {timeout}s; "
        "the loop may not be locked, so the receipts and quotes may complete on time instead of stalling"
    ) in capsys.readouterr().out


@pytest.mark.parametrize(
    ("fleet_factory", "expected_lock_wait"),
    [
        (_instant_only_fleet, "wait:1"),
        (_healthy_geo_only_fleet, "wait:1"),
        (lambda: _full_fleet("block", bad_count=1), "wait:0"),
    ],
)
async def test_freeze_scenario_falls_back_to_the_slot_gauge_when_describe_raises(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fleet_factory: Callable[[], Fleet],
    expected_lock_wait: str,
) -> None:
    """When describe() fails, the gate waits for the gauge to drop by the bad activity's slot, plus one
    more only when a rollup holds a slot too (the healthy geo has already finished), then sleeps the
    guard, warning that the gauge cannot tell get_ip from get_location."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=2)

    await starter._submit_freeze_scenario(cast("Client", _FakeClient(events, describe_raises=True)), fleet_factory())

    after_bad = _submission_events(events)[events.index("geo:bad") + 1 :]
    assert after_bad[:3] == ["describe", expected_lock_wait, f"sleep:{FREEZE_LOCK_GUARD_SECONDS}"]
    assert "the gate is approximate" in capsys.readouterr().out


async def test_freeze_scenario_warns_with_the_consequence_when_the_gauge_fallback_times_out(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With describe() failing and the gauge never reaching its target, the starter warns what that means
    for the run and still submits the receipts and quotes after the guard."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=2, slots_reached=False)

    await starter._submit_freeze_scenario(
        cast("Client", _FakeClient(events, describe_raises=True)), _instant_only_fleet()
    )

    assert _submission_events(events) == [
        "geo:bad",
        "describe",
        "wait:1",
        f"sleep:{FREEZE_LOCK_GUARD_SECONDS}",
        "receipt",
        "quote",
    ]
    assert (
        "the loop may not be locked, so the receipts and quotes may complete on time instead of stalling"
        in capsys.readouterr().out
    )


async def test_freeze_scenario_gates_on_started_even_when_metrics_are_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no baseline slot reading, the occupied-slot wait is skipped with a warning, but the healthy
    geo is still awaited and the STARTED gate needs only the server, so both still run."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=None)

    await starter._submit_freeze_scenario(cast("Client", _FakeClient(events)), _full_fleet("cpu", bad_count=1))

    assert _submission_events(events) == [
        "rollup",
        "geo:healthy",
        "result:geo:healthy",
        "geo:bad",
        "describe",
        f"sleep:{FREEZE_LOCK_GUARD_SECONDS}",
        "receipt",
        "quote",
    ]
    assert "metrics endpoint unreachable" in capsys.readouterr().out


async def test_freeze_scenario_sleeps_the_fixed_delay_when_describe_raises_and_metrics_are_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With neither the server nor the metrics endpoint able to confirm the lock, the last resort is a
    blind pause longer than the guard before the instant bystanders."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=None)

    await starter._submit_freeze_scenario(
        cast("Client", _FakeClient(events, describe_raises=True)), _full_fleet("cpu", bad_count=1)
    )

    assert _submission_events(events) == [
        "rollup",
        "geo:healthy",
        "result:geo:healthy",
        "geo:bad",
        "describe",
        f"sleep:{FREEZE_FALLBACK_DELAY_SECONDS}",
        "receipt",
        "quote",
    ]
    assert FREEZE_FALLBACK_DELAY_SECONDS > FREEZE_LOCK_GUARD_SECONDS
    out = capsys.readouterr().out
    assert "the metrics endpoint is unreachable" in out
    assert f"pausing {FREEZE_FALLBACK_DELAY_SECONDS}s blind" in out
    assert "the loop may not be locked" in out
    assert "falling back to the activity slot gauge" not in out


async def test_freeze_scenario_warns_and_clamps_the_wait_when_no_slot_is_free_at_baseline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A prior scenario still holding every slot gives an occupied-slot wait target of 0, never -1, plus
    a warning; the healthy geo await and the STARTED gate still run before the instant bystanders."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=0)

    await starter._submit_freeze_scenario(cast("Client", _FakeClient(events)), _full_fleet("block", bad_count=1))

    assert _submission_events(events) == [
        "rollup",
        "geo:healthy",
        "wait:0",
        "result:geo:healthy",
        "geo:bad",
        "describe",
        f"sleep:{FREEZE_LOCK_GUARD_SECONDS}",
        "receipt",
        "quote",
    ]
    assert "already has no free activity slots" in capsys.readouterr().out


@pytest.mark.parametrize(("bad_count", "expected_target"), [(1, 1), (2, 0), (3, 0)])
async def test_saturation_scenario_waits_for_the_bad_runs_slots_then_submits_every_bystander(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad_count: int,
    expected_target: int,
) -> None:
    """The wait target is the baseline minus the bad runs, floored at zero; healthy geo joins the bystanders."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=2)
    client = _FakeClient(events)

    await starter._submit_saturation_scenario(cast("Client", client), _full_fleet("slow", bad_count=bad_count))

    assert _submission_events(events) == [
        *["geo:bad"] * bad_count,
        f"wait:{expected_target}",
        "receipt",
        "rollup",
        "quote",
        "geo:healthy",
    ]
    assert _reported_labels(capsys.readouterr().out, client)[-bad_count:] == ["geo:bad"] * bad_count


async def test_saturation_scenario_warns_and_skips_the_wait_when_metrics_are_unreachable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With no baseline slot reading, the saturation path warns instead of burning the poll timeout."""
    events: list[str] = []
    _install_slot_fakes(monkeypatch, events, baseline_free=None)

    await starter._submit_saturation_scenario(cast("Client", _FakeClient(events)), _full_fleet("slow", bad_count=2))

    assert not any(event.startswith("wait") for event in events)
    assert "metrics endpoint unreachable" in capsys.readouterr().out


async def _main_succeeds() -> None:
    """Stand in for a starter main() that finishes normally."""


async def _main_raises_runtime_error() -> None:
    """Stand in for a starter main() that fails, for example when the server is down."""
    raise RuntimeError("connection refused")


async def _main_is_interrupted() -> None:
    """Stand in for a starter main() the user stops with Ctrl-C."""
    raise KeyboardInterrupt


async def _main_rejects_its_arguments() -> None:
    """Stand in for argparse rejecting the flags, which exits with status 2."""
    raise SystemExit(2)


@pytest.mark.parametrize(
    ("fake_main", "expected_exit_code"),
    [
        (_main_succeeds, 0),
        (_main_raises_runtime_error, 1),
        (_main_is_interrupted, 130),
        (_main_rejects_its_arguments, 2),
    ],
)
def test_run_main_turns_every_outcome_into_an_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    fake_main: Callable[[], Coroutine[None, None, None]],
    expected_exit_code: int,
) -> None:
    """run_main never lets an exception escape, so the os._exit teardown always runs after it."""
    monkeypatch.setattr(starter, "main", fake_main)

    assert run_main() == expected_exit_code


def test_run_main_prints_the_traceback_of_a_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A failing run still shows why, even though os._exit skips Python's normal error report."""
    monkeypatch.setattr(starter, "main", _main_raises_runtime_error)

    run_main()

    assert "connection refused" in capsys.readouterr().err
