"""Tests for the plant subentry flow (adding a plant)."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import (
    CONF_AREA_ID,
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SPECIES_PID,
    CONF_SPECIES_SEARCH,
    CONF_WATERING_INTERVAL,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.plant_care.openplantbook import (
    OpenPlantbookAuthError,
    OpenPlantbookError,
    OpenPlantbookRateLimitError,
    SpeciesMatch,
)

MONSTERA = SpeciesMatch(
    pid="monstera deliciosa",
    display_pid="Monstera deliciosa",
    alias="swiss cheese plant",
)
ADANSONII = SpeciesMatch(
    pid="monstera adansonii", display_pid="Monstera adansonii", alias=""
)


@pytest.fixture
def hub_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_CLIENT_ID: "my-id", CONF_CLIENT_SECRET: "secret"}
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_search() -> Iterator[AsyncMock]:
    """Stand in for the OpenPlantbook species search."""
    with patch(
        "custom_components.plant_care.config_flow.OpenPlantbookClient.async_search",
        autospec=True,
        return_value=[MONSTERA, ADANSONII],
    ) as search:
        yield search


async def _start(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PLANT), context={"source": SOURCE_USER}
    )


async def _configure(hass: HomeAssistant, result: Any, data: dict[str, Any]) -> Any:
    return await hass.config_entries.subentries.async_configure(result["flow_id"], data)


def _fields(result: Any) -> set[str]:
    return {str(key) for key in result["data_schema"].schema}


async def test_add_plant_without_species(
    hass: HomeAssistant, hub_entry: MockConfigEntry, mock_search: AsyncMock
) -> None:
    """Without search text the details step has no species and the plant is created."""
    result = await _start(hass, hub_entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await _configure(hass, result, {CONF_NAME: "Ficus"})
    assert result["step_id"] == "details"
    assert CONF_SPECIES_PID not in _fields(result)
    mock_search.assert_not_awaited()

    result = await _configure(
        hass,
        result,
        {
            CONF_LOCATION_TYPE: "indoor",
            CONF_WATERING_INTERVAL: 7,
            CONF_FEEDING_INTERVAL: 30,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ficus"
    assert result["data"] == {
        CONF_NAME: "Ficus",
        CONF_LOCATION_TYPE: "indoor",
        CONF_WATERING_INTERVAL: 7,
        CONF_FEEDING_INTERVAL: 30,
    }
    (subentry,) = hub_entry.subentries.values()
    assert subentry.subentry_type == SUBENTRY_TYPE_PLANT
    assert subentry.title == "Ficus"


async def test_add_plant_with_found_species(
    hass: HomeAssistant, hub_entry: MockConfigEntry, mock_search: AsyncMock
) -> None:
    """Search results become species options; the chosen PID and extras are stored."""
    result = await _start(hass, hub_entry)
    result = await _configure(
        hass, result, {CONF_NAME: "Monstera", CONF_SPECIES_SEARCH: "monstera"}
    )

    assert result["step_id"] == "details"
    assert mock_search.await_args is not None
    assert mock_search.await_args.args[1] == "monstera"
    species_selector = result["data_schema"].schema[CONF_SPECIES_PID]
    assert species_selector.config["options"] == [
        {
            "value": "monstera deliciosa",
            "label": "Monstera deliciosa (swiss cheese plant)",
        },
        {"value": "monstera adansonii", "label": "Monstera adansonii"},
    ]

    result = await _configure(
        hass,
        result,
        {
            CONF_SPECIES_PID: "monstera deliciosa",
            CONF_LOCATION_TYPE: "outdoor",
            CONF_AREA_ID: "balcony",
            CONF_SOIL_MOISTURE_ENTITY: "sensor.monstera_moisture",
            CONF_WEATHER_ENTITY: "weather.balcony",
            CONF_WATERING_INTERVAL: 5,
            CONF_FEEDING_INTERVAL: 21,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_NAME: "Monstera",
        CONF_SPECIES_PID: "monstera deliciosa",
        CONF_LOCATION_TYPE: "outdoor",
        CONF_AREA_ID: "balcony",
        CONF_SOIL_MOISTURE_ENTITY: "sensor.monstera_moisture",
        CONF_WEATHER_ENTITY: "weather.balcony",
        CONF_WATERING_INTERVAL: 5,
        CONF_FEEDING_INTERVAL: 21,
    }


async def test_species_can_be_left_empty_after_search(
    hass: HomeAssistant, hub_entry: MockConfigEntry, mock_search: AsyncMock
) -> None:
    """Picking no species from the results adds the plant without one."""
    result = await _start(hass, hub_entry)
    result = await _configure(
        hass, result, {CONF_NAME: "Mystery", CONF_SPECIES_SEARCH: "monstera"}
    )

    result = await _configure(
        hass,
        result,
        {
            CONF_LOCATION_TYPE: "indoor",
            CONF_WATERING_INTERVAL: 7,
            CONF_FEEDING_INTERVAL: 30,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_SPECIES_PID not in result["data"]


async def test_details_have_defaults(
    hass: HomeAssistant, hub_entry: MockConfigEntry, mock_search: AsyncMock
) -> None:
    """Location and intervals are prefilled."""
    result = await _start(hass, hub_entry)
    result = await _configure(hass, result, {CONF_NAME: "Ficus"})

    defaults = {
        str(key): key.default()
        for key in result["data_schema"].schema
        if callable(key.default)
    }
    assert defaults == {
        CONF_LOCATION_TYPE: "indoor",
        CONF_WATERING_INTERVAL: 7,
        CONF_FEEDING_INTERVAL: 30,
    }


async def test_search_without_matches(
    hass: HomeAssistant, hub_entry: MockConfigEntry, mock_search: AsyncMock
) -> None:
    """No matches keeps the user on step one with a field error."""
    mock_search.return_value = []
    result = await _start(hass, hub_entry)

    result = await _configure(
        hass, result, {CONF_NAME: "Ficus", CONF_SPECIES_SEARCH: "nothing"}
    )

    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_SPECIES_SEARCH: "no_species_found"}


@pytest.mark.parametrize(
    ("exc", "error"),
    [
        (OpenPlantbookAuthError(), "invalid_auth"),
        (OpenPlantbookRateLimitError(), "rate_limited"),
        (OpenPlantbookError(), "cannot_connect"),
    ],
)
async def test_search_errors_allow_continuing_without_species(
    hass: HomeAssistant,
    hub_entry: MockConfigEntry,
    mock_search: AsyncMock,
    exc: Exception,
    error: str,
) -> None:
    """A failed search shows an error; clearing the search text continues."""
    mock_search.side_effect = exc
    result = await _start(hass, hub_entry)

    result = await _configure(
        hass, result, {CONF_NAME: "Ficus", CONF_SPECIES_SEARCH: "ficus"}
    )
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}

    result = await _configure(hass, result, {CONF_NAME: "Ficus"})
    assert result["step_id"] == "details"
