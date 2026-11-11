"""ABOUTME: The flood plan and the closing summary for the exercise 06 starter, as pure functions.
ABOUTME: No I/O and no Temporal import: the starter feeds in numbers and records and prints the lines.

The flood plan says when each receipt is due: receipt ``index`` is due ``index / rate`` seconds after
the flood starts, for as long as the flood lasts. The summary turns the receipts' records into the
totals and a timeline. The timeline groups receipts by submit time relative to a zero point (the
confirmed freeze, or the end of the lead in a healthy flood) into 5-second buckets, and gives each
bucket its count, its failures, its receipts slower than 2 seconds, and its median and slowest
latency.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from itertools import count, takewhile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

BUCKET_SECONDS: int = 5
"""Width of one timeline bucket, in seconds of submit time."""

SLOW_THRESHOLD_SECONDS: float = 2.0
"""A receipt that took longer than this from submit to close counts as slow."""


@dataclass(frozen=True)
class ReceiptRecord:
    """What happened to one receipt the flood submitted.

    Attributes:
        submit_offset: Seconds from the start of the flood to the receipt's submit.
        latency_seconds: Seconds from its submit until it completed or failed.
        failed: Whether the workflow failed.
        failure_message: The failure's message when it failed, otherwise None.
    """

    submit_offset: float
    latency_seconds: float
    failed: bool
    failure_message: str | None


@dataclass(frozen=True)
class Bucket:
    """One 5-second slice of the timeline, by submit time relative to the zero point.

    Attributes:
        index: The bucket's position: 0 covers +0s up to +5s, -1 covers -5s up to +0s.
        count: Receipts submitted in this slice.
        failed: How many of them failed.
        slow: How many took longer than SLOW_THRESHOLD_SECONDS, failed ones included.
        median_seconds: Their median latency, or None for an empty bucket.
        max_seconds: Their slowest latency, or None for an empty bucket.
    """

    index: int
    count: int
    failed: int
    slow: int
    median_seconds: float | None
    max_seconds: float | None

    @property
    def start_seconds(self) -> int:
        """The slice's first second relative to the zero point."""
        return self.index * BUCKET_SECONDS

    @property
    def end_seconds(self) -> int:
        """The second relative to the zero point where the slice ends."""
        return self.start_seconds + BUCKET_SECONDS


@dataclass(frozen=True)
class FloodSummary:
    """The flood's totals and its timeline.

    Attributes:
        submitted: Receipts submitted.
        failed: How many of them failed.
        first_failure_message: The failure message of the earliest submitted failed receipt, or None.
        buckets: Every bucket from the first receipt's to the last receipt's, in order, empty ones included.
    """

    submitted: int
    failed: int
    first_failure_message: str | None
    buckets: list[Bucket]


def due_time(index: int, rate: float) -> float:
    """Return when receipt number index is due, in seconds from the start of the flood.

    Args:
        index: The receipt's position in the flood, from 0.
        rate: Receipts per second.

    Returns:
        The receipt's due time.
    """
    return index / rate


def flood_due_times(rate: float, duration_seconds: float) -> list[float]:
    """Return the due time of every receipt in a flood of the given rate and length.

    Args:
        rate: Receipts per second.
        duration_seconds: How long the flood lasts; a receipt due at or after it is not part of it.

    Returns:
        The due times in order, from 0.0, each 1 / rate seconds after the one before.
    """
    due_times = (due_time(index, rate) for index in count())
    return list(takewhile(lambda due: due < duration_seconds, due_times))


def planned_duration(lead: float, block_seconds: float, tail: float) -> float:
    """Return the length of a healthy flood: the lead, the block, and the tail together.

    Args:
        lead: Seconds of flood before the bad run would be submitted.
        block_seconds: How long the bad run's lock would be held.
        tail: Seconds of flood after the bad run would return.

    Returns:
        The flood's length in seconds.
    """
    return lead + block_seconds + tail


def _bucket(index: int, records: Sequence[ReceiptRecord]) -> Bucket:
    """Count one bucket's receipts, failures, and slow receipts, and take their median and slowest latency."""
    latencies = [record.latency_seconds for record in records]
    return Bucket(
        index=index,
        count=len(records),
        failed=sum(record.failed for record in records),
        slow=sum(latency > SLOW_THRESHOLD_SECONDS for latency in latencies),
        median_seconds=statistics.median(latencies) if latencies else None,
        max_seconds=max(latencies, default=None),
    )


def summarize(records: Sequence[ReceiptRecord], freeze_offset: float) -> FloodSummary:
    """Total the receipts and bucket them by submit time relative to the zero point.

    Args:
        records: One record per submitted receipt, in any order.
        freeze_offset: The zero point of the timeline, in seconds from the start of the flood.

    Returns:
        The totals and every bucket from the first receipt's to the last receipt's.
    """
    # Group the records by bucket index; floor puts a receipt submitted exactly at the zero point in bucket 0.
    by_index: dict[int, list[ReceiptRecord]] = {}
    for record in records:
        index = math.floor((record.submit_offset - freeze_offset) / BUCKET_SECONDS)
        by_index.setdefault(index, []).append(record)

    # Fill every index between the first and the last, so an empty slice still shows.
    buckets = []
    if by_index:
        buckets = [_bucket(index, by_index.get(index, [])) for index in range(min(by_index), max(by_index) + 1)]

    failures = sorted((record for record in records if record.failed), key=lambda record: record.submit_offset)
    return FloodSummary(
        submitted=len(records),
        failed=len(failures),
        first_failure_message=failures[0].failure_message if failures else None,
        buckets=buckets,
    )


def format_bucket(bucket: Bucket) -> str:
    """Format one timeline line, for example ``submitted  -5s..  +0s n=50 failed=1 slow>2s=3 p50=0.37s max=9.81s``.

    Args:
        bucket: The bucket to format.

    Returns:
        The line, with ``-`` for the median and slowest of an empty bucket.
    """
    median = "-" if bucket.median_seconds is None else f"{bucket.median_seconds:.2f}s"
    slowest = "-" if bucket.max_seconds is None else f"{bucket.max_seconds:.2f}s"
    return (
        f"submitted{bucket.start_seconds:+4d}s..{bucket.end_seconds:+4d}s n={bucket.count} failed={bucket.failed} "
        f"slow>{SLOW_THRESHOLD_SECONDS:g}s={bucket.slow} p50={median} max={slowest}"
    )


def format_summary(
    summary: FloodSummary,
    outcomes: Sequence[tuple[str, str]] = (),
    zero_point: str = "the confirmed freeze",
) -> list[str]:
    """Format the closing summary: the totals, the named runs' outcomes, then the timeline.

    Args:
        summary: The flood's totals and timeline from summarize.
        outcomes: One (run name, outcome) pair per rollup and bad run, printed in order.
        zero_point: What the timeline's +0s is, for its heading, for example "the end of the lead".

    Returns:
        The summary's lines, without line endings.
    """
    first_failure = summary.first_failure_message or "none"
    return [
        f"receipts submitted={summary.submitted} failed={summary.failed}",
        f"first failure: {first_failure}",
        *(f"{name}: {outcome}" for name, outcome in outcomes),
        f"timeline by submit time, relative to {zero_point}:",
        *(format_bucket(bucket) for bucket in summary.buckets),
    ]
