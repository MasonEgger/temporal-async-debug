"""ABOUTME: Tests for the flood plan and the closing summary, both pure functions in flood.py.
ABOUTME: Nothing here touches a server or Temporal; every input is a number or a hand-built ReceiptRecord.
"""

from __future__ import annotations

import pytest
from flood import (
    Bucket,
    FloodSummary,
    ReceiptRecord,
    flood_due_times,
    format_summary,
    planned_duration,
    summarize,
)

FREEZE_OFFSET: float = 12.0
"""A confirmed freeze 12 seconds into the flood, the zero point of the hand-built timelines below."""


def _record(submit_offset: float, latency_seconds: float = 0.4, failure_message: str | None = None) -> ReceiptRecord:
    """Build one receipt's record; a failure message marks it failed."""
    return ReceiptRecord(
        submit_offset=submit_offset,
        latency_seconds=latency_seconds,
        failed=failure_message is not None,
        failure_message=failure_message,
    )


def _bucket(summary: FloodSummary, index: int) -> Bucket:
    """Return the summary's bucket with the given index."""
    return next(bucket for bucket in summary.buckets if bucket.index == index)


def test_the_default_flood_plan_spaces_500_receipts_a_tenth_of_a_second_apart() -> None:
    """Ten receipts per second for 50 seconds is 500 due times, from 0.0, 0.1 seconds apart."""
    due_times = flood_due_times(rate=10, duration_seconds=50)

    assert len(due_times) == 500
    assert due_times[0] == 0.0
    gaps = [later - earlier for earlier, later in zip(due_times, due_times[1:], strict=False)]
    assert gaps == pytest.approx([0.1] * 499)


def test_planned_duration_is_the_lead_the_block_and_the_tail() -> None:
    """The default lead, block, and tail add up to a 50-second flood."""
    assert planned_duration(lead=10, block_seconds=30, tail=10) == 50


def test_a_fractional_duration_stops_before_its_end() -> None:
    """Four receipts per second over 2.5 seconds is 10 due times, the last at 2.25 seconds."""
    due_times = flood_due_times(rate=4, duration_seconds=2.5)

    assert len(due_times) == 10
    assert due_times[-1] == pytest.approx(2.25)


def test_a_receipt_submitted_before_the_freeze_lands_in_the_bucket_ending_at_zero() -> None:
    """Three seconds before the freeze is bucket -1 (-5s..+0s); exactly at the freeze is bucket 0 (+0s..+5s)."""
    summary = summarize([_record(FREEZE_OFFSET - 3), _record(FREEZE_OFFSET)], freeze_offset=FREEZE_OFFSET)

    assert [(bucket.index, bucket.count) for bucket in summary.buckets] == [(-1, 1), (0, 1)]
    assert (_bucket(summary, -1).start_seconds, _bucket(summary, -1).end_seconds) == (-5, 0)
    assert (_bucket(summary, 0).start_seconds, _bucket(summary, 0).end_seconds) == (0, 5)


def test_failed_and_slow_counts_median_and_slowest_are_per_bucket() -> None:
    """Each bucket counts its own failures and receipts over 2 seconds, and reports its own median and slowest."""
    records = [
        # Bucket -1: three fast receipts.
        _record(FREEZE_OFFSET - 4, 0.3),
        _record(FREEZE_OFFSET - 3, 0.5),
        _record(FREEZE_OFFSET - 2, 0.4),
        # Bucket 0: one fast, one slow, one failed after 10.5 seconds.
        _record(FREEZE_OFFSET + 1, 0.2),
        _record(FREEZE_OFFSET + 2, 6.0),
        _record(FREEZE_OFFSET + 3, 10.5, failure_message="activity ScheduleToClose timeout"),
    ]

    summary = summarize(records, freeze_offset=FREEZE_OFFSET)

    before, during = _bucket(summary, -1), _bucket(summary, 0)
    assert (before.count, before.failed, before.slow) == (3, 0, 0)
    assert (before.median_seconds, before.max_seconds) == (0.4, 0.5)
    assert (during.count, during.failed, during.slow) == (3, 1, 2)
    assert (during.median_seconds, during.max_seconds) == (6.0, 10.5)


def test_a_bucket_with_no_receipts_between_the_first_and_the_last_is_still_returned() -> None:
    """A gap in the timeline shows as a bucket with a count of 0, so the timeline has no holes."""
    summary = summarize([_record(FREEZE_OFFSET + 1), _record(FREEZE_OFFSET + 11)], freeze_offset=FREEZE_OFFSET)

    assert [(bucket.index, bucket.count) for bucket in summary.buckets] == [(0, 1), (1, 0), (2, 1)]
    empty = _bucket(summary, 1)
    assert (empty.failed, empty.slow, empty.median_seconds, empty.max_seconds) == (0, 0, None, None)


def test_the_totals_count_every_receipt_and_keep_the_earliest_submitted_failure() -> None:
    """The totals report how many were submitted and failed, and the failure message of the earliest submitted."""
    records = [
        _record(FREEZE_OFFSET + 4, 10.2, failure_message="second failure"),
        _record(FREEZE_OFFSET - 1),
        _record(FREEZE_OFFSET + 2, 10.1, failure_message="first failure"),
    ]

    summary = summarize(records, freeze_offset=FREEZE_OFFSET)

    assert (summary.submitted, summary.failed, summary.first_failure_message) == (3, 2, "first failure")


def test_a_run_with_no_failure_reports_none() -> None:
    """With every receipt completed, the failed count is 0 and there is no first failure message."""
    summary = summarize([_record(1.0), _record(2.0)], freeze_offset=FREEZE_OFFSET)

    assert (summary.submitted, summary.failed, summary.first_failure_message) == (2, 0, None)


def test_a_bucket_line_matches_the_timeline_format() -> None:
    """A bucket with receipts prints its range, counts, median, and slowest in the timeline's fixed format."""
    bucket = Bucket(index=-1, count=50, failed=1, slow=3, median_seconds=0.37, max_seconds=9.81)

    lines = format_summary(FloodSummary(submitted=50, failed=1, first_failure_message="boom", buckets=[bucket]))

    assert "submitted  -5s..  +0s n=50 failed=1 slow>2s=3 p50=0.37s max=9.81s" in lines


def test_an_empty_bucket_line_prints_no_latency() -> None:
    """A bucket with no receipts prints its range and zero counts, with no median or slowest to report."""
    bucket = Bucket(index=2, count=0, failed=0, slow=0, median_seconds=None, max_seconds=None)

    lines = format_summary(FloodSummary(submitted=0, failed=0, first_failure_message=None, buckets=[bucket]))

    assert "submitted +10s.. +15s n=0 failed=0 slow>2s=0 p50=- max=-" in lines


def test_the_summary_opens_with_the_totals_then_the_outcomes_then_the_timeline() -> None:
    """The closing summary prints the totals, each named run's outcome, and then the timeline, in that order."""
    summary = summarize(
        [_record(FREEZE_OFFSET - 1), _record(FREEZE_OFFSET + 1, 10.4, failure_message="activity timeout")],
        freeze_offset=FREEZE_OFFSET,
    )

    lines = format_summary(
        summary,
        outcomes=[("rollup rollup-1", "FAILED: activity timeout"), ("geo geo-1", "completed")],
        zero_point="the confirmed freeze",
    )

    assert lines == [
        "receipts submitted=2 failed=1",
        "first failure: activity timeout",
        "rollup rollup-1: FAILED: activity timeout",
        "geo geo-1: completed",
        "timeline by submit time, relative to the confirmed freeze:",
        "submitted  -5s..  +0s n=1 failed=0 slow>2s=0 p50=0.40s max=0.40s",
        "submitted  +0s..  +5s n=1 failed=1 slow>2s=1 p50=10.40s max=10.40s",
    ]
