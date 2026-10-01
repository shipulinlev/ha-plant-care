"""Tests for the climate multiplier."""

import pytest

from custom_components.plant_care.core.climate_factor import climate_multiplier
from custom_components.plant_care.core.models import (
    ClimateReading,
    ClimateStatus,
    SpeciesProfile,
)

PROFILE = SpeciesProfile(min_temp=15, max_temp=30, min_env_humid=40, max_env_humid=80)


def _mult(reading: ClimateReading, profile: SpeciesProfile | None = PROFILE) -> float:
    return climate_multiplier(reading, profile, 0.5, 1.5)[0]


def _status(
    reading: ClimateReading, profile: SpeciesProfile | None = PROFILE
) -> ClimateStatus:
    return climate_multiplier(reading, profile, 0.5, 1.5)[1]


def test_within_range_is_neutral() -> None:
    reading = ClimateReading(temperature=22, humidity=60)
    assert _mult(reading) == 1.0
    assert _status(reading) is ClimateStatus.OK


def test_hotter_than_range_shortens_interval() -> None:
    # 3 degrees over a 15-degree range: 20% shorter.
    reading = ClimateReading(temperature=33)
    assert _mult(reading) == pytest.approx(0.8)
    assert _status(reading) is ClimateStatus.OUT_OF_RANGE


def test_colder_than_range_lengthens_interval() -> None:
    assert _mult(ClimateReading(temperature=12)) == pytest.approx(1.2)


def test_drier_than_range_shortens_interval() -> None:
    # 10% below a 40-point range: 25% shorter.
    assert _mult(ClimateReading(humidity=30)) == pytest.approx(0.75)


def test_more_humid_than_range_lengthens_interval() -> None:
    assert _mult(ClimateReading(humidity=90)) == pytest.approx(1.25)


def test_factors_combine() -> None:
    assert _mult(ClimateReading(temperature=33, humidity=30)) == pytest.approx(0.6)


def test_multiplier_is_clamped() -> None:
    assert _mult(ClimateReading(temperature=60, humidity=0)) == 0.5
    assert _mult(ClimateReading(temperature=-30, humidity=100)) == 1.5


def test_no_readings_is_unknown() -> None:
    assert _mult(ClimateReading()) == 1.0
    assert _status(ClimateReading()) is ClimateStatus.UNKNOWN


def test_no_profile_is_unknown() -> None:
    reading = ClimateReading(temperature=40, humidity=10)
    assert _mult(reading, None) == 1.0
    assert _status(reading, None) is ClimateStatus.UNKNOWN


def test_incomplete_range_is_skipped() -> None:
    profile = SpeciesProfile(max_temp=30, min_env_humid=40, max_env_humid=80)
    reading = ClimateReading(temperature=40, humidity=60)
    assert _mult(reading, profile) == 1.0
    assert _status(reading, profile) is ClimateStatus.OK


def test_degenerate_range_is_skipped() -> None:
    profile = SpeciesProfile(min_temp=20, max_temp=20)
    assert _status(ClimateReading(temperature=25), profile) is ClimateStatus.UNKNOWN
