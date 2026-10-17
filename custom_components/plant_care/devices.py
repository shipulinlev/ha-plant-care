"""One device per plant: creation, naming, species model, one-time area handoff."""

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr

from .const import CONF_AREA_ID, CONF_SPECIES_PID, DOMAIN
from .plants import plant_subentries
from .storage import ProfileCache


@callback
def async_sync_plant_devices(
    hass: HomeAssistant, entry: ConfigEntry, profiles: ProfileCache
) -> None:
    """Create or update the device of every plant subentry.

    Removed plants need nothing here: HA deletes the devices of a removed
    subentry itself.
    """
    device_registry = dr.async_get(hass)
    for subentry in plant_subentries(entry):
        device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry.subentry_id,
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            model=_species_name(subentry, profiles),
        )
        if CONF_AREA_ID in subentry.data:
            _apply_pending_area(hass, entry, subentry, device)


@callback
def async_update_species_models(
    hass: HomeAssistant, entry: ConfigEntry, profiles: ProfileCache
) -> None:
    """Show each plant's species name once its profile has been fetched."""
    device_registry = dr.async_get(hass)
    for subentry in plant_subentries(entry):
        device = device_registry.async_get_device_by_identifier(
            (DOMAIN, subentry.subentry_id), entry.entry_id
        )
        if device is not None:
            device_registry.async_update_device(
                device.id, model=_species_name(subentry, profiles)
            )


def _species_name(subentry: ConfigSubentry, profiles: ProfileCache) -> str | None:
    """The readable species name from the cached profile, else the PID."""
    pid: str | None = subentry.data.get(CONF_SPECIES_PID)
    if not pid:
        return None
    profile = profiles.get(pid)
    return (profile.display_pid if profile else None) or pid


@callback
def _apply_pending_area(
    hass: HomeAssistant,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
    device: dr.DeviceEntry,
) -> None:
    """Move the area chosen in the add flow onto the device, then forget it.

    The add flow cannot know the new subentry_id, so it parks the area in the
    subentry data; from here on the device registry is its only home.
    """
    area_id = subentry.data[CONF_AREA_ID]
    if ar.async_get(hass).async_get_area(area_id) is not None:
        dr.async_get(hass).async_update_device(device.id, area_id=area_id)
    hass.config_entries.async_update_subentry(
        entry,
        subentry,
        data={
            key: value for key, value in subentry.data.items() if key != CONF_AREA_ID
        },
    )
