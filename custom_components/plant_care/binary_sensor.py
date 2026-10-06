"""Binary sensors of a plant: whether it needs water or feeding now."""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
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

_NEEDS_CARE = frozenset({CareStatus.DUE, CareStatus.OVERDUE})


@dataclass(frozen=True, kw_only=True)
class PlantBinarySensorDescription(BinarySensorEntityDescription):
    """Which care status of a plan the binary sensor follows."""

    status_fn: Callable[[CarePlan], CareStatus | None]


BINARY_SENSORS: tuple[PlantBinarySensorDescription, ...] = (
    PlantBinarySensorDescription(
        key="needs_water",
        status_fn=lambda plan: plan.watering_status,
    ),
    PlantBinarySensorDescription(
        key="needs_feeding",
        status_fn=lambda plan: plan.feeding_status,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlantCareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors of every plant, each set bound to its plant subentry."""
    coordinator = entry.runtime_data.coordinator
    for subentry in plant_subentries(entry):
        async_add_entities(
            [
                PlantBinarySensor(coordinator, subentry.subentry_id, description)
                for description in BINARY_SENSORS
            ],
            config_subentry_id=subentry.subentry_id,
        )


class PlantBinarySensor(PlantCareEntity, BinarySensorEntity):
    """On while a care action of one plant is due or overdue."""

    entity_description: PlantBinarySensorDescription

    def __init__(
        self,
        coordinator: PlantCareCoordinator,
        plant_id: str,
        description: PlantBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, plant_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Whether the care is due; unknown while nothing is scheduled."""
        plan = self.plan
        status = self.entity_description.status_fn(plan) if plan else None
        return status in _NEEDS_CARE if status is not None else None
