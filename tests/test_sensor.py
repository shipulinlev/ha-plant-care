"""Tests for the plant sensors."""

from datetime import timedelta

from homeassistant.components.sensor import ATTR_OPTIONS, SensorDeviceClass
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_NAME,
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

KEYS = (
    "next_watering",
    "next_feeding",
    "watering_status",
    "feeding_status",
    "last_watered",
    "last_fed",
)


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


async def test_sensors_belong_to_the_plant(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Each sensor is named after the plant and bound to its device and subentry."""
    (subentry_id,) = entry.subentries
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), entry.entry_id
    )
    assert device is not None
    registry = er.async_get(hass)

    for key in KEYS:
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{subentry_id}_{key}"
        )
        assert entity_id == f"sensor.ficus_{key}"
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.device_id == device.id
        assert entity.config_subentry_id == subentry_id
        assert entity.translation_key == key


async def test_nothing_scheduled_without_history(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A new plant has no dates and no status yet."""
    for key in KEYS:
        state = hass.states.get(f"sensor.ficus_{key}")
        assert state is not None
        assert state.state == STATE_UNKNOWN


async def test_logged_watering_fills_the_sensors(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """After a watering, last/next dates and the status are shown."""
    (subentry_id,) = entry.subentries
    watered_at = (dt_util.utcnow() - timedelta(days=1)).replace(microsecond=0)

    await entry.runtime_data.coordinator.async_log_care(
        CareEvent(plant_id=subentry_id, kind=CareKind.WATERED, at=watered_at)
    )
    await hass.async_block_till_done()

    last = hass.states.get("sensor.ficus_last_watered")
    assert last is not None
    assert dt_util.parse_datetime(last.state) == watered_at
    assert last.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.TIMESTAMP
    upcoming = hass.states.get("sensor.ficus_next_watering")
    assert upcoming is not None
    assert dt_util.parse_datetime(upcoming.state) == watered_at + timedelta(days=7)
    status = hass.states.get("sensor.ficus_watering_status")
    assert status is not None
    assert status.state == "ok"
    assert status.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.ENUM
    assert status.attributes[ATTR_OPTIONS] == ["ok", "soon", "due", "overdue"]
    assert status.attributes["climate_status"] == "unknown"
    assert "explanation" in status.attributes


async def test_overdue_feeding_status(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """A feeding long past its interval shows as overdue."""
    (subentry_id,) = entry.subentries

    await entry.runtime_data.coordinator.async_log_care(
        CareEvent(
            plant_id=subentry_id,
            kind=CareKind.FED,
            at=dt_util.utcnow() - timedelta(days=200),
        )
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.ficus_feeding_status")
    assert state is not None
    assert state.state == "overdue"
