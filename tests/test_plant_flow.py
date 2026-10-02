"""Tests for the plant subentry flow (adding a plant)."""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER, ConfigSubentryData
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
        "custom_components.plant_care.flow_helpers.OpenPlantbookClient.async_search",
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


OLD_PLANT = {
    CONF_NAME: "Monstera",
    CONF_SPECIES_PID: "monstera deliciosa",
    CONF_LOCATION_TYPE: "indoor",
    CONF_SOIL_MOISTURE_ENTITY: "sensor.monstera_moisture",
    CONF_WATERING_INTERVAL: 7,
    CONF_FEEDING_INTERVAL: 30,
    "min_temp": 12.0,
}
NEW_DETAILS = {
    CONF_LOCATION_TYPE: "outdoor",
    CONF_WEATHER_ENTITY: "weather.balcony",
    CONF_WATERING_INTERVAL: 4,
    CONF_FEEDING_INTERVAL: 14,
    "min_temp": 15.0,
    "max_temp": 30.0,
}


def _hub_with_plant(hass: HomeAssistant, plant: dict[str, Any]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CLIENT_ID: "my-id", CONF_CLIENT_SECRET: "secret"},
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
    return entry


def _suggested(result: Any) -> dict[str, Any]:
    return {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }


async def test_reconfigure_keeps_species_and_replaces_details(
    hass: HomeAssistant, mock_search: AsyncMock
) -> None:
    """Without a new search the species stays; details and overrides are replaced."""
    entry = _hub_with_plant(hass, OLD_PLANT)
    (subentry_id,) = entry.subentries

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    assert result["step_id"] == "reconfigure"
    assert _suggested(result) == {CONF_NAME: "Monstera"}

    result = await _configure(hass, result, {CONF_NAME: "Big monstera"})
    assert result["step_id"] == "reconfigure_details"
    assert CONF_SPECIES_PID not in _fields(result)
    assert CONF_AREA_ID not in _fields(result)
    assert _suggested(result) == {
        key: value
        for key, value in OLD_PLANT.items()
        if key not in (CONF_NAME, CONF_SPECIES_PID)
    }
    mock_search.assert_not_awaited()

    result = await _configure(hass, result, NEW_DETAILS)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = entry.subentries[subentry_id]
    assert subentry.title == "Big monstera"
    assert dict(subentry.data) == {
        CONF_NAME: "Big monstera",
        CONF_SPECIES_PID: "monstera deliciosa",
        **NEW_DETAILS,
    }


async def test_reconfigure_with_search_changes_species(
    hass: HomeAssistant, mock_search: AsyncMock
) -> None:
    """A new search offers the matches and stores the chosen species."""
    entry = _hub_with_plant(hass, OLD_PLANT)
    (subentry_id,) = entry.subentries
    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)

    result = await _configure(
        hass, result, {CONF_NAME: "Monstera", CONF_SPECIES_SEARCH: "adansonii"}
    )
    assert CONF_SPECIES_PID in _fields(result)

    result = await _configure(
        hass, result, {CONF_SPECIES_PID: "monstera adansonii", **NEW_DETAILS}
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[subentry_id].data[CONF_SPECIES_PID] == "monstera adansonii"


async def test_reconfigure_rejects_inverted_range(
    hass: HomeAssistant, mock_search: AsyncMock
) -> None:
    """A minimum above its maximum is a form error and nothing is saved."""
    entry = _hub_with_plant(hass, OLD_PLANT)
    (subentry_id,) = entry.subentries
    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await _configure(hass, result, {CONF_NAME: "Monstera"})

    result = await _configure(
        hass, result, {**NEW_DETAILS, "min_temp": 31.0, "max_temp": 30.0}
    )

    assert result["step_id"] == "reconfigure_details"
    assert result["errors"] == {"base": "invalid_range"}
    assert dict(entry.subentries[subentry_id].data) == OLD_PLANT


async def test_reconfigure_keeps_pending_area_handoff(
    hass: HomeAssistant, mock_search: AsyncMock
) -> None:
    """An area not yet applied to the device survives a reconfigure."""
    entry = _hub_with_plant(hass, {**OLD_PLANT, CONF_AREA_ID: "kitchen"})
    (subentry_id,) = entry.subentries
    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await _configure(hass, result, {CONF_NAME: "Monstera"})

    result = await _configure(hass, result, NEW_DETAILS)

    assert entry.subentries[subentry_id].data[CONF_AREA_ID] == "kitchen"


async def test_reconfigure_search_then_empty_species_removes_it(
    hass: HomeAssistant, mock_search: AsyncMock
) -> None:
    """After a new search, leaving the species empty drops the old one."""
    entry = _hub_with_plant(hass, OLD_PLANT)
    (subentry_id,) = entry.subentries
    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await _configure(
        hass, result, {CONF_NAME: "Monstera", CONF_SPECIES_SEARCH: "monstera"}
    )

    result = await _configure(hass, result, NEW_DETAILS)

    assert result["reason"] == "reconfigure_successful"
    assert CONF_SPECIES_PID not in entry.subentries[subentry_id].data
