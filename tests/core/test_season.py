"""Tests for the seasonal feeding factor."""

from datetime import UTC, datetime

import pytest

from custom_components.plant_care.core.season import Season, season_at

MOSCOW = 55.7
SYDNEY = -33.9


@pytest.mark.parametrize(
    ("month", "latitude", "expected"),
    [
        (1, MOSCOW, Season.WINTER),
        (4, MOSCOW, Season.SPRING),
        (7, MOSCOW, Season.SUMMER),
        (10, MOSCOW, Season.AUTUMN),
        (12, MOSCOW, Season.WINTER),
        (1, SYDNEY, Season.SUMMER),
        (4, SYDNEY, Season.AUTUMN),
        (7, SYDNEY, Season.WINTER),
        (10, SYDNEY, Season.SPRING),
    ],
)
def test_season_by_month_and_hemisphere(
    month: int, latitude: float, expected: Season
) -> None:
    assert season_at(datetime(2026, month, 15, tzinfo=UTC), latitude) is expected


def test_feeding_factor_slows_down_in_autumn_and_winter() -> None:
    assert Season.SPRING.feeding_factor == 1.0
    assert Season.SUMMER.feeding_factor == 1.0
    assert Season.AUTUMN.feeding_factor == 1.5
    assert Season.WINTER.feeding_factor == 2.0
