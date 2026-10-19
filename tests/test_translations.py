"""Translations stay complete: en mirrors strings.json, ru has every key."""

from collections.abc import Iterator
import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER, ConfigSubentryData
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NAME
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import (
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_SPECIES_PID,
    CONF_SPECIES_SEARCH,
    CONF_WATERING_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.plant_care.openplantbook import SpeciesMatch

INTEGRATION = Path(__file__).parents[1] / "custom_components" / DOMAIN
PLACEHOLDER = re.compile(r"\{\w+\}")


def _load(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((INTEGRATION / name).read_text("utf-8"))
    return result


def _leaves(tree: dict[str, Any], prefix: str = "") -> Iterator[tuple[str, str]]:
    for key, value in tree.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _leaves(value, path)
        else:
            yield path, value


STRINGS = _load("strings.json")


def test_en_matches_strings() -> None:
    """translations/en.json is a copy of strings.json."""
    assert _load("translations/en.json") == STRINGS


def test_ru_has_exactly_the_same_keys() -> None:
    """Every English string has a Russian one, and nothing extra."""
    assert {path for path, _ in _leaves(_load("translations/ru.json"))} == {
        path for path, _ in _leaves(STRINGS)
    }


def test_ru_keeps_placeholders() -> None:
    """Russian strings use the same {placeholders} as the English ones."""
    russian = dict(_leaves(_load("translations/ru.json")))
    for path, english in _leaves(STRINGS):
        assert sorted(PLACEHOLDER.findall(russian[path])) == sorted(
            PLACEHOLDER.findall(english)
        ), path


def _assert_fields_labelled(result: Any, step_strings: dict[str, Any]) -> None:
    fields = {str(key) for key in result["data_schema"].schema}
    assert fields <= set(step_strings["data"]), result["step_id"]


@pytest.fixture
def hub(hass: HomeAssistant) -> MockConfigEntry:
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
    return entry


@pytest.fixture(autouse=True)
def mock_search() -> Iterator[None]:
    with patch(
        "custom_components.plant_care.flow_helpers.OpenPlantbookClient.async_search",
        return_value=[SpeciesMatch(pid="ficus", display_pid="Ficus", alias="")],
    ):
        yield


async def test_hub_steps_label_every_field(
    hass: HomeAssistant, hub: MockConfigEntry
) -> None:
    """Hub reconfigure (the user step shares its schema) labels every field."""
    steps = STRINGS["config"]["step"]
    result = await hub.start_reconfigure_flow(hass)
    _assert_fields_labelled(result, steps["reconfigure"])
    assert set(steps["user"]["data"]) == set(steps["reconfigure"]["data"])


async def test_plant_steps_label_every_field(
    hass: HomeAssistant, hub: MockConfigEntry
) -> None:
    """Every plant flow step, species dropdown included, labels every field."""
    steps = STRINGS["config_subentries"]["plant"]["step"]
    search = {CONF_NAME: "Ficus", CONF_SPECIES_SEARCH: "ficus"}

    result = await hass.config_entries.subentries.async_init(
        (hub.entry_id, SUBENTRY_TYPE_PLANT), context={"source": SOURCE_USER}
    )
    _assert_fields_labelled(result, steps["user"])
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], search
    )
    _assert_fields_labelled(result, steps["details"])

    (subentry_id,) = hub.subentries
    result = await hub.start_subentry_reconfigure_flow(hass, subentry_id)
    _assert_fields_labelled(result, steps["reconfigure"])
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {**search, CONF_WATERING_INTERVAL: 7, CONF_FEEDING_INTERVAL: 30},
    )
    assert result["step_id"] == "reconfigure"
    assert result["data_schema"] is not None
    assert CONF_SPECIES_PID in result["data_schema"].schema
    _assert_fields_labelled(result, steps["reconfigure"])
