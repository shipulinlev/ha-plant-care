"""Tests for CareEngine: how the factors combine into a CarePlan."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.plant_care.core.engine import CareEngine
from custom_components.plant_care.core.models import (
    CareEvent,
    CareKind,
    CarePlan,
    CareStatus,
    ClimateReading,
    ClimateStatus,
    LocationType,
    PlantConfig,
    Precipitation,
    SpeciesProfile,
)

NOW = datetime(2026, 6, 15, 12, tzinfo=UTC)  # northern summer
MOSCOW = 55.7
DAY = timedelta(days=1)

INDOOR = PlantConfig(
    plant_id="p1",
    location_type=LocationType.INDOOR,
    initial_watering_interval_days=7,
    feeding_interval_days=14,
)
OUTDOOR = PlantConfig(
    plant_id="p1",
    location_type=LocationType.OUTDOOR,
    initial_watering_interval_days=7,
    feeding_interval_days=14,
)
PROFILE = SpeciesProfile(
    min_temp=15,
    max_temp=30,
    min_env_humid=40,
    max_env_humid=80,
    min_soil_moist=20,
    max_soil_moist=60,
)


def _watered(days_ago: float) -> CareEvent:
    return CareEvent(plant_id="p1", kind=CareKind.WATERED, at=NOW - days_ago * DAY)


def _fed(days_ago: float) -> CareEvent:
    return CareEvent(plant_id="p1", kind=CareKind.FED, at=NOW - days_ago * DAY)


def _rain(days_from_now: float, mm: float) -> Precipitation:
    return Precipitation(at=NOW + days_from_now * DAY, amount_mm=mm)


def _plan(
    events: Sequence[CareEvent] = (),
    *,
    plant: PlantConfig = INDOOR,
    climate: ClimateReading | None = None,
    profile: SpeciesProfile | None = PROFILE,
    now: datetime = NOW,
    latitude: float = MOSCOW,
) -> CarePlan:
    return CareEngine().plan(
        plant=plant,
        events=events,
        climate=climate or ClimateReading(),
        profile=profile,
        now=now,
        latitude=latitude,
    )


# --- watering: history -------------------------------------------------------


def test_no_history_gives_no_schedule() -> None:
    plan = _plan()
    assert plan.last_watered is None
    assert plan.next_watering is None
    assert plan.watering_status is None
    assert "no watering logged" in plan.explanation


def test_single_watering_uses_initial_interval() -> None:
    plan = _plan([_watered(2)])
    assert plan.last_watered == NOW - 2 * DAY
    assert plan.next_watering == NOW + 5 * DAY
    assert plan.watering_status is CareStatus.OK
    assert "initial interval" in plan.explanation


def test_history_median_interval() -> None:
    plan = _plan([_watered(d) for d in (13, 9, 6, 2)])  # intervals 4, 3, 4
    assert plan.next_watering == NOW + 2 * DAY
    assert "median of 3 intervals" in plan.explanation


def test_overdue_watering() -> None:
    assert _plan([_watered(9)]).watering_status is CareStatus.OVERDUE


def test_future_and_duplicate_events_are_ignored() -> None:
    events = [_watered(2), _watered(2 - 1 / 1440), _watered(-1)]
    plan = _plan(events)
    assert plan.last_watered == NOW - 2 * DAY
    assert plan.next_watering == NOW + 5 * DAY


# --- watering: climate ---------------------------------------------------------


def test_hot_climate_shortens_interval() -> None:
    # 33 degrees: 20% over the range, interval 7 d -> 5.6 d.
    plan = _plan([_watered(0)], climate=ClimateReading(temperature=33))
    assert plan.next_watering == NOW + 5.6 * DAY
    assert plan.climate_status is ClimateStatus.OUT_OF_RANGE
    assert "climate x0.80" in plan.explanation


def test_missing_climate_keeps_base_interval() -> None:
    plan = _plan([_watered(0)])
    assert plan.next_watering == NOW + 7 * DAY
    assert plan.climate_status is ClimateStatus.UNKNOWN


def test_missing_profile_keeps_base_interval() -> None:
    plan = _plan([_watered(0)], climate=ClimateReading(temperature=40), profile=None)
    assert plan.next_watering == NOW + 7 * DAY
    assert plan.climate_status is ClimateStatus.UNKNOWN


# --- watering: precipitation -------------------------------------------------


def test_past_rain_counts_as_watering_outdoors() -> None:
    climate = ClimateReading(precipitation=(_rain(-1, 10),))
    plan = _plan([_watered(5)], plant=OUTDOOR, climate=climate)
    assert plan.next_watering == NOW + 6 * DAY
    assert plan.last_watered == NOW - 5 * DAY  # rain is not logged care
    assert "rain" in plan.explanation


def test_light_rain_is_ignored() -> None:
    climate = ClimateReading(precipitation=(_rain(-1, 2),))
    plan = _plan([_watered(5)], plant=OUTDOOR, climate=climate)
    assert plan.next_watering == NOW + 2 * DAY


def test_forecast_rain_before_due_date_postpones_watering() -> None:
    climate = ClimateReading(precipitation=(_rain(1, 8), _rain(3, 8)))
    plan = _plan([_watered(5)], plant=OUTDOOR, climate=climate)
    # Due in 2 days, but rain in 1 day waters the plant (next: 1 + 7 days),
    # and the rain in 3 days restarts the interval again: 3 + 7 days.
    assert plan.next_watering == NOW + 10 * DAY


def test_forecast_rain_after_due_date_does_not_help() -> None:
    climate = ClimateReading(precipitation=(_rain(3, 8),))
    plan = _plan([_watered(5)], plant=OUTDOOR, climate=climate)
    assert plan.next_watering == NOW + 2 * DAY


def test_rain_without_logged_watering_starts_schedule() -> None:
    climate = ClimateReading(precipitation=(_rain(-3, 8),))
    plan = _plan(plant=OUTDOOR, climate=climate)
    assert plan.next_watering == NOW + 4 * DAY


def test_indoor_plants_ignore_rain() -> None:
    climate = ClimateReading(precipitation=(_rain(-1, 20),))
    assert _plan([_watered(5)], climate=climate).next_watering == NOW + 2 * DAY


# --- watering: soil sensor ---------------------------------------------------


def test_dry_soil_means_water_now() -> None:
    plan = _plan([_watered(1)], climate=ClimateReading(soil_moisture=10))
    assert plan.next_watering == NOW
    assert plan.watering_status is CareStatus.DUE
    assert "soil dry" in plan.explanation


def test_dry_soil_without_history_means_water_now() -> None:
    plan = _plan(climate=ClimateReading(soil_moisture=10))
    assert plan.next_watering == NOW
    assert plan.watering_status is CareStatus.DUE


def test_dry_soil_keeps_overdue_status() -> None:
    plan = _plan([_watered(10)], climate=ClimateReading(soil_moisture=10))
    assert plan.watering_status is CareStatus.OVERDUE


def test_wet_soil_means_no_watering_needed() -> None:
    plan = _plan([_watered(10)], climate=ClimateReading(soil_moisture=70))
    assert plan.next_watering == NOW + DAY
    assert plan.watering_status is CareStatus.OK
    assert "soil wet" in plan.explanation


def test_wet_soil_keeps_later_schedule() -> None:
    plan = _plan([_watered(0)], climate=ClimateReading(soil_moisture=70))
    assert plan.next_watering == NOW + 7 * DAY


def test_soil_within_range_uses_schedule() -> None:
    plan = _plan([_watered(10)], climate=ClimateReading(soil_moisture=40))
    assert plan.watering_status is CareStatus.OVERDUE


def test_soil_sensor_without_species_range_is_ignored() -> None:
    profile = SpeciesProfile(min_temp=15, max_temp=30)
    plan = _plan(
        [_watered(1)], climate=ClimateReading(soil_moisture=5), profile=profile
    )
    assert plan.next_watering == NOW + 6 * DAY


# --- feeding -----------------------------------------------------------------


def test_no_feeding_history_gives_no_schedule() -> None:
    plan = _plan()
    assert plan.last_fed is None
    assert plan.next_feeding is None
    assert plan.feeding_status is None


def test_feeding_in_growing_season() -> None:
    plan = _plan([_fed(10)])
    assert plan.last_fed == NOW - 10 * DAY
    assert plan.next_feeding == NOW + 4 * DAY
    assert plan.feeding_status is CareStatus.OK


@pytest.mark.parametrize(
    ("latitude", "next_in_days"),
    [(MOSCOW, 18), (-33.9, 4)],  # January: winter in the north, summer in the south
)
def test_feeding_seasonal_factor(latitude: float, next_in_days: float) -> None:
    now = datetime(2026, 1, 15, 12, tzinfo=UTC)
    event = CareEvent(plant_id="p1", kind=CareKind.FED, at=now - 10 * DAY)
    plan = _plan([event], now=now, latitude=latitude)
    assert plan.next_feeding == now + next_in_days * DAY


def test_feeding_due() -> None:
    assert _plan([_fed(14)]).feeding_status is CareStatus.DUE
