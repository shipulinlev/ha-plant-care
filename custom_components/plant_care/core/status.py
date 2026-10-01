"""Classify how urgent a scheduled care action is."""

from datetime import datetime, timedelta

from .models import CareStatus


def care_status(
    next_at: datetime,
    now: datetime,
    *,
    soon_window: timedelta,
    overdue_after: timedelta,
) -> CareStatus:
    """Status of a care action scheduled at `next_at`."""
    if now >= next_at + overdue_after:
        return CareStatus.OVERDUE
    if now >= next_at:
        return CareStatus.DUE
    if next_at - now <= soon_window:
        return CareStatus.SOON
    return CareStatus.OK
