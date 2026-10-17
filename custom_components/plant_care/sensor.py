"""Sensors of a plant: next and last care dates, intervals, care statuses."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PlantCareCoordinator
from .core.models import CarePlan, CareStatus
from .entity import PlantCareEntity
from .plants import plant_subentries
from .runtime import PlantCareConfigEntry

# Entities only read coordinator data.
PARALLEL_UPDATES = 0

_STATUS_OPTIONS = [status.value for status in CareStatus]

# Days between care events behind the next date, for the Lovelace cards.
ATTR_INTERVAL_DAYS: Final = "interval_days"


@dataclass(frozen=True, kw_only=True)
class PlantSensorDescription(SensorEntityDescription):
    """How a sensor reads its value (and extra attributes) from a care plan."""

    value_fn: Callable[[CarePlan], datetime | str | None]
    attributes_fn: Callable[[CarePlan], Mapping[str, Any]] | None = None
    # Shows the species photo, so a card can find it on a known entity.
    species_picture: bool = False


def _status(status: CareStatus | None) -> str | None:
    return status.value if status is not None else None


def _interval(interval: timedelta | None) -> dict[str, float]:
    """The interval in days, left out while unknown."""
    if interval is None:
        return {}
    return {ATTR_INTERVAL_DAYS: round(interval / timedelta(days=1), 2)}


SENSORS: tuple[PlantSensorDescription, ...] = (
    PlantSensorDescription(
        key="next_watering",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda plan: plan.next_watering,
        attributes_fn=lambda plan: _interval(plan.watering_interval),
        species_picture=True,
    ),
    PlantSensorDescription(
        key="next_feeding",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda plan: plan.next_feeding,
        attributes_fn=lambda plan: _interval(plan.feeding_interval),
    ),
    PlantSensorDescription(
        key="watering_status",
        device_class=SensorDeviceClass.ENUM,
        options=_STATUS_OPTIONS,
        value_fn=lambda plan: _status(plan.watering_status),
        attributes_fn=lambda plan: {
            "climate_status": plan.climate_status.value,
            "explanation": plan.explanation,
        },
    ),
    PlantSensorDescription(
        key="feeding_status",
        device_class=SensorDeviceClass.ENUM,
        options=_STATUS_OPTIONS,
        value_fn=lambda plan: _status(plan.feeding_status),
    ),
    PlantSensorDescription(
        key="last_watered",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda plan: plan.last_watered,
    ),
    PlantSensorDescription(
        key="last_fed",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda plan: plan.last_fed,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlantCareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors of every plant, each set bound to its plant subentry."""
    coordinator = entry.runtime_data.coordinator
    for subentry in plant_subentries(entry):
        async_add_entities(
            [
                PlantSensor(coordinator, subentry.subentry_id, description)
                for description in SENSORS
            ],
            config_subentry_id=subentry.subentry_id,
        )


class PlantSensor(PlantCareEntity, SensorEntity):
    """A care date or status of one plant."""

    entity_description: PlantSensorDescription
    # The explanation changes on every update; keep it out of the recorder.
    _unrecorded_attributes = frozenset({"explanation"})

    def __init__(
        self,
        coordinator: PlantCareCoordinator,
        plant_id: str,
        description: PlantSensorDescription,
    ) -> None:
        super().__init__(coordinator, plant_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> datetime | str | None:
        """The value from the current plan."""
        plan = self.plan
        return self.entity_description.value_fn(plan) if plan else None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Extra plan details, for sensors that define them."""
        plan = self.plan
        attributes_fn = self.entity_description.attributes_fn
        return attributes_fn(plan) if plan and attributes_fn else None

    @property
    def entity_picture(self) -> str | None:
        """The species photo from the cached OpenPlantbook profile."""
        if not self.entity_description.species_picture:
            return None
        profile = self.coordinator.species_profile(self._plant_id)
        return profile.image_url if profile else None
