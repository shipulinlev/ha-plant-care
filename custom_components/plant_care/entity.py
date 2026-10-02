"""Base class of all plant entities."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PlantCareCoordinator
from .core.models import CarePlan


class PlantCareEntity(CoordinatorEntity[PlantCareCoordinator]):
    """An entity of one plant, attached to the plant's device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PlantCareCoordinator, plant_id: str, key: str
    ) -> None:
        super().__init__(coordinator)
        self._plant_id = plant_id
        self._attr_unique_id = f"{plant_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, plant_id)})

    @property
    def plan(self) -> CarePlan | None:
        """The plant's current care plan."""
        return self.coordinator.data.get(self._plant_id)

    @property
    def available(self) -> bool:
        """Available while the coordinator has a plan for this plant."""
        return super().available and self.plan is not None
