"""Buttons of a plant: log a watering or a feeding now."""

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PlantCareCoordinator
from .core.models import CareEvent, CareKind
from .entity import PlantCareEntity
from .plants import plant_subentries
from .runtime import PlantCareConfigEntry

# A press only appends to the in-memory care log; there is no device to protect.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PlantButtonDescription(ButtonEntityDescription):
    """Which care a button logs."""

    kind: CareKind


BUTTONS: tuple[PlantButtonDescription, ...] = (
    PlantButtonDescription(key="water", kind=CareKind.WATERED),
    PlantButtonDescription(key="feed", kind=CareKind.FED),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlantCareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the buttons of every plant, each set bound to its plant subentry."""
    coordinator = entry.runtime_data.coordinator
    for subentry in plant_subentries(entry):
        async_add_entities(
            [
                PlantButton(coordinator, subentry.subentry_id, description)
                for description in BUTTONS
            ],
            config_subentry_id=subentry.subentry_id,
        )


class PlantButton(PlantCareEntity, ButtonEntity):
    """Logs a watering or a feeding of one plant at the moment of the press."""

    entity_description: PlantButtonDescription

    def __init__(
        self,
        coordinator: PlantCareCoordinator,
        plant_id: str,
        description: PlantButtonDescription,
    ) -> None:
        super().__init__(coordinator, plant_id, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Log the care now."""
        await self.coordinator.async_log_care(
            CareEvent(
                plant_id=self._plant_id,
                kind=self.entity_description.kind,
                at=dt_util.utcnow(),
            )
        )
