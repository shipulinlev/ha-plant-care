"""Data models shared by the engine and the integration."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class LocationType(StrEnum):
    """Where a plant lives; picks the climate source."""

    INDOOR = "indoor"
    OUTDOOR = "outdoor"


class CareKind(StrEnum):
    """Kind of care the user logged."""

    WATERED = "watered"
    FED = "fed"


class CareStatus(StrEnum):
    """How urgent the next watering or feeding is."""

    OK = "ok"
    SOON = "soon"
    DUE = "due"
    OVERDUE = "overdue"


class ClimateStatus(StrEnum):
    """Whether the current climate fits the species range."""

    OK = "ok"
    OUT_OF_RANGE = "out_of_range"
    UNKNOWN = "unknown"


def _require_aware(at: datetime) -> None:
    if at.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlantConfig:
    """User settings of one plant (from its config subentry)."""

    plant_id: str
    location_type: LocationType
    initial_watering_interval_days: float
    feeding_interval_days: float


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeciesProfile:
    """Acceptable environment ranges of a species; any bound may be unknown."""

    min_temp: float | None = None
    max_temp: float | None = None
    min_env_humid: float | None = None
    max_env_humid: float | None = None
    min_soil_moist: float | None = None
    max_soil_moist: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CareEvent:
    """One logged watering or feeding."""

    plant_id: str
    kind: CareKind
    at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.at)


@dataclass(frozen=True, slots=True, kw_only=True)
class Precipitation:
    """Rain amount at a point in time (observed or forecast)."""

    at: datetime
    amount_mm: float

    def __post_init__(self) -> None:
        _require_aware(self.at)


@dataclass(frozen=True, slots=True, kw_only=True)
class ClimateReading:
    """Current conditions around a plant; every value is optional."""

    temperature: float | None = None
    humidity: float | None = None
    soil_moisture: float | None = None
    precipitation: tuple[Precipitation, ...] = field(default=())


@dataclass(frozen=True, slots=True, kw_only=True)
class CarePlan:
    """Engine output for one plant."""

    last_watered: datetime | None
    last_fed: datetime | None
    next_watering: datetime | None
    next_feeding: datetime | None
    watering_status: CareStatus | None
    feeding_status: CareStatus | None
    climate_status: ClimateStatus
    explanation: str
