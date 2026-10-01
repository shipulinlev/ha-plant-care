"""Tests for care status classification."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.plant_care.core.models import CareStatus
from custom_components.plant_care.core.status import care_status

NOW = datetime(2026, 6, 15, 12, tzinfo=UTC)
DAY = timedelta(days=1)


@pytest.mark.parametrize(
    ("next_in", "expected"),
    [
        (timedelta(days=3), CareStatus.OK),
        (timedelta(hours=25), CareStatus.OK),
        (DAY, CareStatus.SOON),
        (timedelta(hours=1), CareStatus.SOON),
        (timedelta(0), CareStatus.DUE),
        (-timedelta(hours=23), CareStatus.DUE),
        (-DAY, CareStatus.OVERDUE),
        (-timedelta(days=5), CareStatus.OVERDUE),
    ],
)
def test_care_status(next_in: timedelta, expected: CareStatus) -> None:
    assert care_status(NOW + next_in, NOW, soon_window=DAY, overdue_after=DAY) is (
        expected
    )
