"""Tests for loading the Plant Care integration."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import DOMAIN


async def test_integration_manifest(hass: HomeAssistant) -> None:
    """The integration is discovered from custom_components with a valid manifest."""
    integration = await async_get_integration(hass, DOMAIN)

    assert integration.domain == "plant_care"
    assert integration.name == "Plant Care"
    assert integration.version is not None
    assert integration.requirements == []


async def test_async_setup(hass: HomeAssistant) -> None:
    """The integration sets up without YAML configuration."""
    assert await async_setup_component(hass, DOMAIN, {})


async def test_hub_entry_loads_and_unloads(hass: HomeAssistant) -> None:
    """A hub config entry sets up and unloads cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CLIENT_ID: "my-id", CONF_CLIENT_SECRET: "my-secret"},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    # Re-read: mypy keeps entry.state narrowed to LOADED from the assert above.
    unloaded = hass.config_entries.async_get_entry(entry.entry_id)
    assert unloaded is not None
    assert unloaded.state is ConfigEntryState.NOT_LOADED
