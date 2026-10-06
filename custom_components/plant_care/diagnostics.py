"""Diagnostics: what each plant's plan was computed from, without credentials."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_SPECIES_PID, DOMAIN
from .plants import plant_subentries
from .runtime import PlantCareConfigEntry

TO_REDACT = {CONF_CLIENT_ID, CONF_CLIENT_SECRET}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PlantCareConfigEntry
) -> dict[str, Any]:
    """Hub settings, each plant's inputs and plan, and the cached species."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    devices = dr.async_get(hass)
    plants: dict[str, Any] = {}
    pids: set[str] = set()
    for subentry in plant_subentries(entry):
        plant_id = subentry.subentry_id
        device = devices.async_get_device_by_identifier(
            (DOMAIN, plant_id), entry.entry_id
        )
        plan = coordinator.data.get(plant_id)
        plants[plant_id] = {
            "title": subentry.title,
            "area_id": device.area_id if device else None,
            "data": dict(subentry.data),
            "care_log": [
                {"kind": event.kind, "at": event.at}
                for event in runtime.care_log.events(plant_id)
            ],
            "plan": asdict(plan) if plan else None,
        }
        if pid := subentry.data.get(CONF_SPECIES_PID):
            pids.add(pid)
    return {
        "hub": async_redact_data(dict(entry.data), TO_REDACT),
        "plants": plants,
        "species_profiles": {
            pid: asdict(profile)
            for pid in sorted(pids)
            if (profile := coordinator.profile_cache.get(pid)) is not None
        },
    }
