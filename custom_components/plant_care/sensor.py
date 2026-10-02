"""Sensors of a plant: next and last care dates, care statuses."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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


@dataclass(frozen=True, kw_only=True)
class PlantSensorDescription(SensorEntityDescription):
    """How a sensor reads its value (and extra attributes) from a care plan."""

    value_fn: Callable[[CarePlan], datetime | str | None]
    attributes_fn: Callable[[CarePlan], Mapping[str, Any]] | None = None


def _status(status: CareStatus | None) -> str | None:
    return status.value if status is not None else None


SENSORS: tuple[PlantSensorDescription, ...] = (
    PlantSensorDescription(
        key="next_watering",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda plan: plan.next_watering,
    ),
    PlantSensorDescription(
        key="next_feeding",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda plan: plan.next_feeding,
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
