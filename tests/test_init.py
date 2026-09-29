"""Tests for loading the Plant Care integration."""

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_setup_component

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
