"""Meteorological seasons and their effect on feeding."""

from datetime import datetime
from enum import StrEnum


class Season(StrEnum):
    """Meteorological season at the plant's location."""

    SPRING = "spring"
    SUMMER = "summer"
    AUTUMN = "autumn"
    WINTER = "winter"

    @property
    def feeding_factor(self) -> float:
        """Multiplier for the feeding interval: plants grow slower off-season."""
        return _FEEDING_FACTORS[self]


_FEEDING_FACTORS = {
    Season.SPRING: 1.0,
    Season.SUMMER: 1.0,
    Season.AUTUMN: 1.5,
    Season.WINTER: 2.0,
}

# Index = month % 12 // 3, northern hemisphere: Dec-Feb, Mar-May, Jun-Aug, Sep-Nov.
_NORTHERN = (Season.WINTER, Season.SPRING, Season.SUMMER, Season.AUTUMN)


def season_at(at: datetime, latitude: float) -> Season:
    """Season at `at`; the southern hemisphere is shifted by half a year."""
    index = at.month % 12 // 3
    if latitude < 0:
        index = (index + 2) % 4
    return _NORTHERN[index]
