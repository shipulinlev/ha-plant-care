"""Tests for the species name shown as the plant device's model."""

from http import HTTPStatus
from typing import Any

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.plant_care.const import (
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_SPECIES_PID,
    CONF_WATERING_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.plant_care.openplantbook import BASE_URL
from custom_components.plant_care.storage import PROFILE_CACHE_STORAGE_KEY

PLANT = {
    CONF_NAME: "Ficus",
    CONF_LOCATION_TYPE: "indoor",
    CONF_WATERING_INTERVAL: 7,
    CONF_FEEDING_INTERVAL: 30,
}
DETAIL_URL = f"{BASE_URL}/plant/detail/ficus/"


@pytest.fixture(autouse=True)
def token(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(
        f"{BASE_URL}/token/", json={"access_token": "t", "expires_in": 3600}
    )


async def _model(hass: HomeAssistant, plant: dict[str, Any]) -> str | None:
    """Set up a hub with one plant and return its device's model."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CLIENT_ID: "id", CONF_CLIENT_SECRET: "secret"},
        subentries_data=[
            ConfigSubentryData(
                data=plant,
                subentry_type=SUBENTRY_TYPE_PLANT,
                title=plant[CONF_NAME],
                unique_id=None,
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    (subentry_id,) = entry.subentries
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), entry.entry_id
    )
    assert device is not None
    return device.model


async def test_plant_without_species_has_no_model(hass: HomeAssistant) -> None:
    """Without a species there is nothing to show."""
    assert await _model(hass, PLANT) is None


async def test_model_is_the_readable_species_name(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A new plant's model is OpenPlantbook's display name, fetched at setup."""
    aioclient_mock.get(
        DETAIL_URL, json={"display_pid": "Ficus benjamina", "min_temp": 10}
    )

    assert await _model(hass, {**PLANT, CONF_SPECIES_PID: "ficus"}) == (
        "Ficus benjamina"
    )


async def test_model_falls_back_to_pid_while_name_is_unknown(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """With OpenPlantbook down and nothing cached, the PID is still shown."""
    aioclient_mock.get(DETAIL_URL, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    assert await _model(hass, {**PLANT, CONF_SPECIES_PID: "ficus"}) == "ficus"


async def test_existing_plant_gets_name_after_upgrade(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A profile cached by an older version (no name) is refetched for the name."""
    hass_storage[PROFILE_CACHE_STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": PROFILE_CACHE_STORAGE_KEY,
        "data": {
            "profiles": {
                "ficus": {
                    "fetched_at": dt_util.utcnow().isoformat(),
                    "profile": {"min_temp": 10.0},
                }
            }
        },
    }
    aioclient_mock.get(
        DETAIL_URL, json={"display_pid": "Ficus benjamina", "min_temp": 10}
    )

    assert await _model(hass, {**PLANT, CONF_SPECIES_PID: "ficus"}) == (
        "Ficus benjamina"
    )
