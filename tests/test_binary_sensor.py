"""Tests for the plant binary sensors."""

from datetime import timedelta

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import (
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_WATERING_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.plant_care.core.models import CareEvent, CareKind

KEYS = ("needs_water", "needs_feeding")
STATUS_OF = {"needs_water": "watering_status", "needs_feeding": "feeding_status"}


@pytest.fixture
async def entry(hass: HomeAssistant) -> MockConfigEntry:
    """A loaded hub with one indoor plant named Ficus."""
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


async def _log(
    hass: HomeAssistant, entry: MockConfigEntry, kind: CareKind, days_ago: float
) -> None:
    (subentry_id,) = entry.subentries
    await entry.runtime_data.coordinator.async_log_care(
        CareEvent(
            plant_id=subentry_id,
            kind=kind,
            at=dt_util.utcnow() - timedelta(days=days_ago),
        )
    )
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, key: str) -> str:
    state = hass.states.get(f"binary_sensor.ficus_{key}")
    assert state is not None
    return state.state


async def test_binary_sensors_belong_to_the_plant(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Each binary sensor is named after the plant, on its device and subentry."""
    (subentry_id,) = entry.subentries
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), entry.entry_id
    )
    assert device is not None
    registry = er.async_get(hass)

    for key in KEYS:
        entity_id = registry.async_get_entity_id(
            "binary_sensor", DOMAIN, f"{subentry_id}_{key}"
        )
        assert entity_id == f"binary_sensor.ficus_{key}"
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.device_id == device.id
        assert entity.config_subentry_id == subentry_id
        assert entity.translation_key == key


async def test_unknown_without_history(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """With nothing scheduled yet, the plant's needs are unknown."""
    for key in KEYS:
        assert _state(hass, key) == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("kind", "key", "days_ago"),
    [
        (CareKind.WATERED, "needs_water", 1),
        (CareKind.WATERED, "needs_water", 6.5),
        (CareKind.FED, "needs_feeding", 1),
    ],
)
async def test_off_before_care_is_due(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    kind: CareKind,
    key: str,
    days_ago: float,
) -> None:
    """Off while the care is ok or only coming soon."""
    await _log(hass, entry, kind, days_ago)

    assert _state(hass, key) == STATE_OFF


@pytest.mark.parametrize(
    ("kind", "key", "days_ago"),
    [
        (CareKind.WATERED, "needs_water", 7.1),
        (CareKind.WATERED, "needs_water", 100),
        (CareKind.FED, "needs_feeding", 200),
    ],
)
async def test_on_when_care_is_due_or_overdue(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    kind: CareKind,
    key: str,
    days_ago: float,
) -> None:
    """On once the care is due, and still on when overdue."""
    await _log(hass, entry, kind, days_ago)

    status = hass.states.get(f"sensor.ficus_{STATUS_OF[key]}")
    assert status is not None
    assert status.state in ("due", "overdue")
    assert _state(hass, key) == STATE_ON
