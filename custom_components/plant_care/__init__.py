"""The Plant Care integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import CONF_PHOTO, DOMAIN
from .coordinator import PlantCareCoordinator
from .devices import async_sync_plant_devices, async_update_species_models
from .flow_helpers import client_from_config
from .photos import async_prune_photos
from .plants import plant_subentries
from .runtime import PlantCareConfigEntry, PlantCareRuntimeData
from .services import async_setup_services
from .storage import CareLog, ProfileCache

# Configured through the UI only; YAML config for the domain is rejected.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.SENSOR,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Plant Care integration: its actions live as long as HA."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PlantCareConfigEntry) -> bool:
    """Set up the hub: plant devices, care history and the coordinator."""
    care_log = CareLog(hass)
    await care_log.async_load()
    for plant_id in care_log.plant_ids() - set(entry.subentries):
        await care_log.async_remove_plant(plant_id)
    # Photos of deleted plants and photos replaced by a new upload.
    await async_prune_photos(
        hass,
        {
            photo
            for subentry in plant_subentries(entry)
            if (photo := subentry.data.get(CONF_PHOTO))
        },
    )
    profile_cache = ProfileCache(hass)
    await profile_cache.async_load()

    async_sync_plant_devices(hass, entry, profile_cache)

    coordinator = PlantCareCoordinator(
        hass,
        entry,
        care_log=care_log,
        profile_cache=profile_cache,
        client=client_from_config(hass, entry.data),
    )
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_listen_registries()

    # A refresh may fetch a species profile, and with it the readable name.
    @callback
    def _update_models() -> None:
        async_update_species_models(hass, entry, profile_cache)

    _update_models()
    entry.async_on_unload(coordinator.async_add_listener(_update_models))
    entry.runtime_data = PlantCareRuntimeData(
        care_log=care_log, coordinator=coordinator
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Registered last: the area handoff above updates subentries, and that
    # must not trigger a reload of the entry being set up.
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlantCareConfigEntry) -> bool:
    """Unload the hub; the coordinator shuts down with the entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: PlantCareConfigEntry) -> None:
    """Apply hub or plant changes (added, edited, removed plants) by reloading."""
    await hass.config_entries.async_reload(entry.entry_id)
