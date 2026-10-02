"""One device per plant: creation, naming and the one-time area handoff."""

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar, device_registry as dr

from .const import CONF_AREA_ID, DOMAIN, SUBENTRY_TYPE_PLANT


@callback
def async_sync_plant_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create or update the device of every plant subentry.

    Removed plants need nothing here: HA deletes the devices of a removed
    subentry itself.
    """
    device_registry = dr.async_get(hass)
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_PLANT:
            continue
        device = device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry.subentry_id,
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
        )
        if CONF_AREA_ID in subentry.data:
            _apply_pending_area(hass, entry, subentry, device)


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
