"""Runtime state of a loaded hub entry."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .coordinator import PlantCareCoordinator
from .storage import CareLog


@dataclass(slots=True)
class PlantCareRuntimeData:
    """Shared objects of the loaded hub, kept in `entry.runtime_data`."""

    care_log: CareLog
    coordinator: PlantCareCoordinator


type PlantCareConfigEntry = ConfigEntry[PlantCareRuntimeData]
