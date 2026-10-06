"""Tests for the config entry diagnostics."""

from datetime import timedelta
import json

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.plant_care.const import DOMAIN
from custom_components.plant_care.core.models import CareEvent, CareKind


async def test_diagnostics_show_plants_without_secrets(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    plant_entry: MockConfigEntry,
) -> None:
    """Hub settings, each plant's inputs and plan; credentials redacted."""
    (subentry_id,) = plant_entry.subentries
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        (DOMAIN, subentry_id), plant_entry.entry_id
    )
    assert device is not None
    devices.async_update_device(device.id, area_id=kitchen)
    watered_at = (dt_util.utcnow() - timedelta(days=1)).replace(microsecond=0)
    await plant_entry.runtime_data.coordinator.async_log_care(
        CareEvent(plant_id=subentry_id, kind=CareKind.WATERED, at=watered_at)
    )
    await hass.async_block_till_done()

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, plant_entry)

    assert '"secret"' not in json.dumps(diagnostics)
    assert diagnostics["hub"] == {"client_id": REDACTED, "client_secret": REDACTED}
    plant = diagnostics["plants"][subentry_id]
    assert isinstance(plant, dict)
    assert plant["title"] == "Ficus"
    assert plant["area_id"] == kitchen
    assert plant["data"]["location_type"] == "indoor"
    assert plant["care_log"] == [{"kind": "watered", "at": watered_at.isoformat()}]
    assert plant["plan"]["watering_status"] == "ok"
    assert plant["plan"]["last_watered"] == watered_at.isoformat()
    assert "explanation" in plant["plan"]
    assert diagnostics["species_profiles"] == {}


async def test_diagnostics_show_cached_species(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    species_entry: MockConfigEntry,
) -> None:
    """The cached profile of each plant's species is included."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, species_entry
    )

    profile = diagnostics["species_profiles"]["ficus"]
    assert isinstance(profile, dict)
    assert profile["min_temp"] == 10
