"""The Plant Care integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import PlantCareCoordinator
from .devices import async_sync_plant_devices
from .flow_helpers import client_from_config
from .runtime import PlantCareConfigEntry, PlantCareRuntimeData
from .storage import CareLog, ProfileCache

# Configured through the UI only; YAML config for the domain is rejected.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Plant Care integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PlantCareConfigEntry) -> bool:
    """Set up the hub: plant devices, care history and the coordinator."""
    care_log = CareLog(hass)
    await care_log.async_load()
    for plant_id in care_log.plant_ids() - set(entry.subentries):
        await care_log.async_remove_plant(plant_id)
    profile_cache = ProfileCache(hass)
    await profile_cache.async_load()

    async_sync_plant_devices(hass, entry)

    coordinator = PlantCareCoordinator(
        hass,
        entry,
        care_log=care_log,
        profile_cache=profile_cache,
        client=client_from_config(hass, entry.data),
    )
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_listen_registries()
    entry.runtime_data = PlantCareRuntimeData(
        care_log=care_log, coordinator=coordinator
    )

    # Registered last: the area handoff above updates subentries, and that
    # must not trigger a reload of the entry being set up.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlantCareConfigEntry) -> bool:
    """Unload the hub; the coordinator shuts down with the entry."""
    return True


async def _async_reload(hass: HomeAssistant, entry: PlantCareConfigEntry) -> None:
    """Apply hub or plant changes (added, edited, removed plants) by reloading."""
    await hass.config_entries.async_reload(entry.entry_id)
