"""Actions: log care, move a plant, refetch its species profile."""

from datetime import datetime

from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
)
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import CONF_AREA_ID, CONF_SPECIES_PID, DOMAIN, SUBENTRY_TYPE_PLANT
from .core.models import CareEvent, CareKind
from .runtime import PlantCareConfigEntry

ATTR_DEVICE_ID = "device_id"
ATTR_WHEN = "when"

SERVICE_WATER = "water"
SERVICE_FEED = "feed"
SERVICE_MOVE = "move"
SERVICE_REFRESH_SPECIES = "refresh_species"

_CARE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_WHEN): cv.datetime,
    }
)
_MOVE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(CONF_AREA_ID): cv.string}
)
_PLANT_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE_ID): cv.string})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's actions."""

    async def water(call: ServiceCall) -> None:
        await _async_log_care(hass, call, CareKind.WATERED)

    async def feed(call: ServiceCall) -> None:
        await _async_log_care(hass, call, CareKind.FED)

    async def move(call: ServiceCall) -> None:
        _plant(hass, call)  # only checks it is a plant of the loaded hub
        area_id = call.data[CONF_AREA_ID]
        if ar.async_get(hass).async_get_area(area_id) is None:
            raise _error("area_not_found", area_id=area_id)
        # The coordinator follows device area changes and recomputes.
        dr.async_get(hass).async_update_device(
            call.data[ATTR_DEVICE_ID], area_id=area_id
        )

    async def refresh_species(call: ServiceCall) -> None:
        entry, subentry = _plant(hass, call)
        pid = subentry.data.get(CONF_SPECIES_PID)
        if not pid:
            raise _error("no_species", plant=subentry.title)
        await entry.runtime_data.coordinator.async_refresh_species(pid)

    for name, handler, schema in (
        (SERVICE_WATER, water, _CARE_SCHEMA),
        (SERVICE_FEED, feed, _CARE_SCHEMA),
        (SERVICE_MOVE, move, _MOVE_SCHEMA),
        (SERVICE_REFRESH_SPECIES, refresh_species, _PLANT_SCHEMA),
    ):
        hass.services.async_register(DOMAIN, name, handler, schema=schema)


async def _async_log_care(
    hass: HomeAssistant, call: ServiceCall, kind: CareKind
) -> None:
    entry, subentry = _plant(hass, call)
    at = _care_time(call.data.get(ATTR_WHEN))
    await entry.runtime_data.coordinator.async_log_care(
        CareEvent(plant_id=subentry.subentry_id, kind=kind, at=at)
    )


def _care_time(when: datetime | None) -> datetime:
    """`when` in UTC (a time without zone is local), now if omitted."""
    now = dt_util.utcnow()
    if when is None:
        return now
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt_util.get_default_time_zone())
    when = dt_util.as_utc(when)
    if when > now:
        raise _error("when_in_future")
    return when


def _plant(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[PlantCareConfigEntry, ConfigSubentry]:
    """The loaded hub and plant subentry of the call's plant device."""
    device_id = call.data[ATTR_DEVICE_ID]
    not_found = _error("plant_not_found", device_id=device_id)
    device = dr.async_get(hass).async_get(device_id)
    if device is None or device.config_subentry_id is None:
        raise not_found
    entry: PlantCareConfigEntry | None = hass.config_entries.async_get_entry(
        device.config_entry_id
    )
    if entry is None or entry.domain != DOMAIN:
        raise not_found
    subentry = entry.subentries.get(device.config_subentry_id)
    if subentry is None or subentry.subentry_type != SUBENTRY_TYPE_PLANT:
        raise not_found
    if entry.state is not ConfigEntryState.LOADED:
        raise _error("hub_not_loaded")
    return entry, subentry


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders or None,
    )
