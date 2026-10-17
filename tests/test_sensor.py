"""Tests for the plant sensors."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_OPTIONS, SensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import DOMAIN
from custom_components.plant_care.core.models import CareEvent, CareKind
from custom_components.plant_care.sensor import ATTR_INTERVAL_DAYS

KEYS = (
    "next_watering",
    "next_feeding",
    "watering_status",
    "feeding_status",
    "last_watered",
    "last_fed",
)


async def test_sensors_belong_to_the_plant(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """Each sensor is named after the plant and bound to its device and subentry."""
    (subentry_id,) = plant_entry.subentries
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), plant_entry.entry_id
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
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """A new plant has no dates and no status yet."""
    for key in KEYS:
        state = hass.states.get(f"sensor.ficus_{key}")
        assert state is not None
        assert state.state == STATE_UNKNOWN


async def test_logged_watering_fills_the_sensors(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """After a watering, last/next dates and the status are shown."""
    (subentry_id,) = plant_entry.subentries
    watered_at = (dt_util.utcnow() - timedelta(days=1)).replace(microsecond=0)

    await plant_entry.runtime_data.coordinator.async_log_care(
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
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """A feeding long past its interval shows as overdue."""
    (subentry_id,) = plant_entry.subentries

    await plant_entry.runtime_data.coordinator.async_log_care(
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


async def test_interval_days_of_a_new_plant(
    hass: HomeAssistant, plant_entry: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    """Before any history: the initial watering and the seasonal feeding interval."""
    freezer.move_to("2026-01-15 12:00:00+00:00")  # winter: feeding x2
    await plant_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    watering = hass.states.get("sensor.ficus_next_watering")
    assert watering is not None
    assert watering.attributes[ATTR_INTERVAL_DAYS] == 7
    feeding = hass.states.get("sensor.ficus_next_feeding")
    assert feeding is not None
    assert feeding.attributes[ATTR_INTERVAL_DAYS] == 60


async def test_interval_days_follows_watering_history(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """With history, the attribute is the learned interval."""
    (subentry_id,) = plant_entry.subentries
    coordinator = plant_entry.runtime_data.coordinator
    for days_ago in (9, 6, 3):
        await coordinator.async_log_care(
            CareEvent(
                plant_id=subentry_id,
                kind=CareKind.WATERED,
                at=dt_util.utcnow() - timedelta(days=days_ago),
            )
        )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.ficus_next_watering")
    assert state is not None
    assert state.attributes[ATTR_INTERVAL_DAYS] == 3


async def test_interval_days_is_left_out_without_a_plan(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """No plan, no interval: the cards hide the field."""
    plant_entry.runtime_data.coordinator.async_set_updated_data({})
    await hass.async_block_till_done()

    for key in ("next_watering", "next_feeding"):
        state = hass.states.get(f"sensor.ficus_{key}")
        assert state is not None
        assert ATTR_INTERVAL_DAYS not in state.attributes
