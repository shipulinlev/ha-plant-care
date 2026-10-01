"""Tests for the core data models."""

from datetime import UTC, datetime

import pytest

from custom_components.plant_care.core.models import (
    CareEvent,
    CareKind,
    CareStatus,
    ClimateStatus,
    LocationType,
    Precipitation,
)


def test_enum_values_are_stable_strings() -> None:
    # These values end up in entity states and storage, so they must not drift.
    assert [s.value for s in CareStatus] == ["ok", "soon", "due", "overdue"]
    assert [s.value for s in ClimateStatus] == ["ok", "out_of_range", "unknown"]
    assert [k.value for k in CareKind] == ["watered", "fed"]
    assert [t.value for t in LocationType] == ["indoor", "outdoor"]


def test_care_event_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        CareEvent(plant_id="p1", kind=CareKind.WATERED, at=datetime(2026, 5, 1))  # noqa: DTZ001


def test_care_event_accepts_aware_datetime() -> None:
    at = datetime(2026, 5, 1, tzinfo=UTC)
    event = CareEvent(plant_id="p1", kind=CareKind.FED, at=at)
    assert event.at == at


def test_precipitation_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Precipitation(at=datetime(2026, 5, 1), amount_mm=3.0)  # noqa: DTZ001
