"""CareEngine: turns config, history, climate and species norms into a CarePlan."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .climate_factor import climate_multiplier
from .history import base_interval, event_times
from .models import (
    CareEvent,
    CareKind,
    CarePlan,
    CareStatus,
    ClimateReading,
    ClimateStatus,
    LocationType,
    PlantConfig,
    SpeciesProfile,
)
from .season import season_at
from .status import care_status


@dataclass(frozen=True, slots=True, kw_only=True)
class EngineSettings:
    """Tunable engine parameters."""

    history_size: int = 5
    multiplier_min: float = 0.5
    multiplier_max: float = 1.5
    rain_threshold_mm: float = 5.0
    soon_window: timedelta = timedelta(days=1)
    overdue_after: timedelta = timedelta(days=1)
    duplicate_window: timedelta = timedelta(hours=6)
    wet_soil_recheck: timedelta = timedelta(days=1)


@dataclass(frozen=True, slots=True)
class _Watering:
    next_at: datetime | None
    status: CareStatus | None
    climate_status: ClimateStatus


class CareEngine:
    """Pure, deterministic care scheduler."""

    def __init__(self, settings: EngineSettings | None = None) -> None:
        self._s = settings or EngineSettings()

    def plan(
        self,
        *,
        plant: PlantConfig,
        events: Sequence[CareEvent],
        climate: ClimateReading,
        profile: SpeciesProfile | None,
        now: datetime,
        latitude: float,
    ) -> CarePlan:
        """Compute the care plan of one plant at `now`."""
        notes: list[str] = []
        watered = event_times(events, CareKind.WATERED, now, self._s.duplicate_window)
        fed = event_times(events, CareKind.FED, now, self._s.duplicate_window)

        watering = self._watering(
            plant, watered, climate=climate, profile=profile, now=now, notes=notes
        )
        next_feeding = self._next_feeding(plant, fed, now, latitude, notes)

        return CarePlan(
            last_watered=watered[-1] if watered else None,
            last_fed=fed[-1] if fed else None,
            next_watering=watering.next_at,
            next_feeding=next_feeding,
            watering_status=watering.status,
            feeding_status=self._status(next_feeding, now),
            climate_status=watering.climate_status,
            explanation="; ".join(notes),
        )

    def _watering(
        self,
        plant: PlantConfig,
        watered: list[datetime],
        *,
        climate: ClimateReading,
        profile: SpeciesProfile | None,
        now: datetime,
        notes: list[str],
    ) -> _Watering:
        base = base_interval(watered, self._s.history_size)
        if base is None:
            base = timedelta(days=plant.initial_watering_interval_days)
            notes.append(f"watering: initial interval {_days(base)}")
        else:
            intervals = min(len(watered) - 1, self._s.history_size)
            notes.append(f"watering: {_days(base)} (median of {intervals} intervals)")

        multiplier, climate_status = climate_multiplier(
            climate, profile, self._s.multiplier_min, self._s.multiplier_max
        )
        if multiplier != 1.0:
            notes.append(f"climate x{multiplier:.2f}")
        interval = base * multiplier

        last = watered[-1] if watered else None
        next_at = last + interval if last else None
        if plant.location_type is LocationType.OUTDOOR:
            next_at = self._apply_rain(climate, last, next_at, interval, notes)
        if next_at is None:
            notes.append("no watering logged")

        return self._apply_soil(
            climate,
            profile,
            next_at=next_at,
            climate_status=climate_status,
            now=now,
            notes=notes,
        )

    def _apply_rain(
        self,
        climate: ClimateReading,
        last: datetime | None,
        next_at: datetime | None,
        interval: timedelta,
        notes: list[str],
    ) -> datetime | None:
        """Heavy enough rain counts as watering and restarts the interval."""
        rains = sorted(
            p.at
            for p in climate.precipitation
            if p.amount_mm >= self._s.rain_threshold_mm
        )
        for at in rains:
            if (last is None or at > last) and (next_at is None or at <= next_at):
                last, next_at = at, at + interval
                notes.append(f"rain {at:%Y-%m-%d} counted as watering")
        return next_at

    def _apply_soil(
        self,
        climate: ClimateReading,
        profile: SpeciesProfile | None,
        *,
        next_at: datetime | None,
        climate_status: ClimateStatus,
        now: datetime,
        notes: list[str],
    ) -> _Watering:
        """A soil moisture reading overrides the heuristic schedule."""
        moisture = climate.soil_moisture
        low = profile.min_soil_moist if profile else None
        high = profile.max_soil_moist if profile else None
        if moisture is not None and low is not None and moisture < low:
            notes.append(f"soil dry ({moisture:g} < {low:g})")
            next_at = now if next_at is None else min(next_at, now)
        elif moisture is not None and high is not None and moisture > high:
            notes.append(f"soil wet ({moisture:g} > {high:g})")
            recheck = now + self._s.wet_soil_recheck
            next_at = recheck if next_at is None else max(next_at, recheck)
            return _Watering(next_at, CareStatus.OK, climate_status)
        return _Watering(next_at, self._status(next_at, now), climate_status)

    def _next_feeding(
        self,
        plant: PlantConfig,
        fed: list[datetime],
        now: datetime,
        latitude: float,
        notes: list[str],
    ) -> datetime | None:
        if not fed:
            notes.append("feeding: none logged")
            return None
        season = season_at(now, latitude)
        interval = timedelta(days=plant.feeding_interval_days) * season.feeding_factor
        notes.append(
            f"feeding: {plant.feeding_interval_days:g} d"
            f" x{season.feeding_factor:g} ({season})"
        )
        return fed[-1] + interval

    def _status(self, next_at: datetime | None, now: datetime) -> CareStatus | None:
        if next_at is None:
            return None
        return care_status(
            next_at,
            now,
            soon_window=self._s.soon_window,
            overdue_after=self._s.overdue_after,
        )


def _days(interval: timedelta) -> str:
    return f"{interval.total_seconds() / 86400:.1f} d"
