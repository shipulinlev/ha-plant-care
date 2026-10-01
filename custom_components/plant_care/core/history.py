"""Helpers that turn the care log into event times and intervals."""

from collections.abc import Iterable
from datetime import datetime, timedelta
from itertools import pairwise
from statistics import median

from .models import CareEvent, CareKind


def event_times(
    events: Iterable[CareEvent],
    kind: CareKind,
    now: datetime,
    duplicate_window: timedelta,
) -> list[datetime]:
    """Return sorted times of past events of one kind.

    Future events are ignored. Events closer than `duplicate_window` to the
    previous kept event count as the same care action.
    """
    times = sorted(e.at for e in events if e.kind is kind and e.at <= now)
    kept: list[datetime] = []
    for at in times:
        if not kept or at - kept[-1] >= duplicate_window:
            kept.append(at)
    return kept


def base_interval(times: list[datetime], history_size: int) -> timedelta | None:
    """Median of the last `history_size` intervals, or None with fewer than 2."""
    intervals = [b - a for a, b in pairwise(times)]
    recent = intervals[-history_size:]
    if len(recent) < 2:
        return None
    return timedelta(seconds=median(i.total_seconds() for i in recent))
