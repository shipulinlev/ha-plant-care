"""Tests for care history helpers."""

from datetime import UTC, datetime, timedelta

from custom_components.plant_care.core.history import base_interval, event_times
from custom_components.plant_care.core.models import CareEvent, CareKind

NOW = datetime(2026, 6, 15, 12, tzinfo=UTC)
DUP = timedelta(hours=6)


def _ev(days_ago: float, kind: CareKind = CareKind.WATERED) -> CareEvent:
    return CareEvent(plant_id="p1", kind=kind, at=NOW - timedelta(days=days_ago))


def test_event_times_sorted_and_filtered_by_kind() -> None:
    events = [_ev(1), _ev(10), _ev(5, CareKind.FED)]
    assert event_times(events, CareKind.WATERED, NOW, DUP) == [
        NOW - timedelta(days=10),
        NOW - timedelta(days=1),
    ]


def test_event_times_ignore_future_events() -> None:
    assert event_times([_ev(2), _ev(-1)], CareKind.WATERED, NOW, DUP) == [
        NOW - timedelta(days=2)
    ]


def test_event_times_merge_duplicates_within_window() -> None:
    # Two presses of the button 10 minutes apart are one watering.
    events = [_ev(3), _ev(3 - 10 / 1440), _ev(3)]
    assert event_times(events, CareKind.WATERED, NOW, DUP) == [NOW - timedelta(days=3)]


def test_base_interval_none_with_fewer_than_two_intervals() -> None:
    times = [NOW - timedelta(days=4), NOW]
    assert base_interval(times, history_size=5) is None
    assert base_interval([], history_size=5) is None


def test_base_interval_median_of_intervals() -> None:
    times = [NOW - timedelta(days=d) for d in (12, 8, 5, 0)]  # intervals 4, 3, 5
    assert base_interval(times, history_size=5) == timedelta(days=4)


def test_base_interval_uses_only_last_n_intervals() -> None:
    # Old intervals of 20 days are ignored; the last three are 2 days.
    times = [NOW - timedelta(days=d) for d in (46, 26, 6, 4, 2, 0)]
    assert base_interval(times, history_size=3) == timedelta(days=2)
