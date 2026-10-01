"""Tests for the hub config flow."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import CONF_WEATHER_ENTITY, DOMAIN
from custom_components.plant_care.openplantbook import (
    OpenPlantbookAuthError,
    OpenPlantbookError,
    OpenPlantbookRateLimitError,
)

CREDENTIALS = {CONF_CLIENT_ID: "my-id", CONF_CLIENT_SECRET: "my-secret"}


@pytest.fixture
def mock_authenticate() -> Iterator[AsyncMock]:
    """Stand in for the OpenPlantbook credential check."""
    with patch(
        "custom_components.plant_care.config_flow.OpenPlantbookClient.async_authenticate",
        autospec=True,
    ) as authenticate:
        yield authenticate


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_authenticate: AsyncMock
) -> None:
    """Valid credentials and a weather entity create the hub entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["description_placeholders"] == {
        "api_keys_url": "https://open.plantbook.io"
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CREDENTIALS, CONF_WEATHER_ENTITY: "weather.home"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Plant Care"
    assert result["data"] == {**CREDENTIALS, CONF_WEATHER_ENTITY: "weather.home"}
    mock_authenticate.assert_awaited_once()


async def test_weather_entity_is_optional(
    hass: HomeAssistant, mock_authenticate: AsyncMock
) -> None:
    """Indoor-only installs can skip the weather entity."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CREDENTIALS


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (OpenPlantbookAuthError(), "invalid_auth"),
        (OpenPlantbookRateLimitError(), "rate_limited"),
        (OpenPlantbookError(), "cannot_connect"),
        (RuntimeError(), "unknown"),
    ],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant,
    mock_authenticate: AsyncMock,
    exc: Exception,
    error: str,
) -> None:
    """A failed check shows a form error, and a retry can still succeed."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    mock_authenticate.side_effect = exc

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_authenticate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_only_one_hub(hass: HomeAssistant) -> None:
    """A second hub cannot be added."""
    MockConfigEntry(domain=DOMAIN, data=CREDENTIALS).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.fixture
def hub_entry(hass: HomeAssistant) -> MockConfigEntry:
    """An existing hub with a default weather entity."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={**CREDENTIALS, CONF_WEATHER_ENTITY: "weather.home"}
    )
    entry.add_to_hass(hass)
    return entry


async def test_reconfigure_updates_hub(
    hass: HomeAssistant, mock_authenticate: AsyncMock, hub_entry: MockConfigEntry
) -> None:
    """Reconfigure re-checks credentials and updates the existing entry."""
    result = await hub_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description
    }
    assert suggested == {**CREDENTIALS, CONF_WEATHER_ENTITY: "weather.home"}

    new_data = {
        CONF_CLIENT_ID: "new-id",
        CONF_CLIENT_SECRET: "new-secret",
        CONF_WEATHER_ENTITY: "weather.garden",
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_data)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert hub_entry.data == new_data
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    mock_authenticate.assert_awaited_once()


async def test_reconfigure_can_clear_weather(
    hass: HomeAssistant, mock_authenticate: AsyncMock, hub_entry: MockConfigEntry
) -> None:
    """Leaving the weather entity empty removes the default."""
    result = await hub_entry.start_reconfigure_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )

    assert result["reason"] == "reconfigure_successful"
    assert hub_entry.data == CREDENTIALS


async def test_reconfigure_error_recovers(
    hass: HomeAssistant, mock_authenticate: AsyncMock, hub_entry: MockConfigEntry
) -> None:
    """Rejected credentials keep the old entry and show an error."""
    result = await hub_entry.start_reconfigure_flow(hass)
    mock_authenticate.side_effect = OpenPlantbookAuthError()
    bad = {CONF_CLIENT_ID: "bad", CONF_CLIENT_SECRET: "bad"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], bad)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert hub_entry.data[CONF_CLIENT_ID] == "my-id"

    mock_authenticate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CREDENTIALS
    )
    assert result["reason"] == "reconfigure_successful"
