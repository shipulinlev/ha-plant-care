"""Shared fixtures for Plant Care tests."""

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NAME
from homeassistant.core import HomeAssistant
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

FICUS_IMAGE = "https://opb-img.plantbook.io/ficus.jpg"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components/."""


@pytest.fixture
async def plant_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A loaded hub with one indoor plant named Ficus (water 7 days, feed 30)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CLIENT_ID: "id", CONF_CLIENT_SECRET: "secret"},
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_NAME: "Ficus",
                    CONF_LOCATION_TYPE: "indoor",
                    CONF_WATERING_INTERVAL: 7,
                    CONF_FEEDING_INTERVAL: 30,
                },
                subentry_type=SUBENTRY_TYPE_PLANT,
                title="Ficus",
                unique_id=None,
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def species_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    """Like `plant_entry`, with species `ficus` from OpenPlantbook.

    The profile has `min_temp` 10, the name "Ficus" and `FICUS_IMAGE`.
    """
    aioclient_mock.post(
        f"{BASE_URL}/token/", json={"access_token": "t", "expires_in": 3600}
    )
    aioclient_mock.get(
        f"{BASE_URL}/plant/detail/ficus/",
        json={"display_pid": "Ficus", "min_temp": 10, "image_url": FICUS_IMAGE},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CLIENT_ID: "id", CONF_CLIENT_SECRET: "secret"},
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_NAME: "Ficus",
                    CONF_SPECIES_PID: "ficus",
                    CONF_LOCATION_TYPE: "indoor",
                    CONF_WATERING_INTERVAL: 7,
                    CONF_FEEDING_INTERVAL: 30,
                },
                subentry_type=SUBENTRY_TYPE_PLANT,
                title="Ficus",
                unique_id=None,
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
