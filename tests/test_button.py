"""Tests for the plant care buttons."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.button.const import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import DOMAIN
from custom_components.plant_care.core.models import CareEvent, CareKind

KEYS = ("water", "feed")


async def _press(hass: HomeAssistant, key: str) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: f"button.ficus_{key}"},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_buttons_belong_to_the_plant(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """Each button is named after the plant, on its device and subentry."""
    (subentry_id,) = plant_entry.subentries
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), plant_entry.entry_id
    )
    assert device is not None
    registry = er.async_get(hass)

    for key in KEYS:
        entity_id = registry.async_get_entity_id(
            "button", DOMAIN, f"{subentry_id}_{key}"
        )
        assert entity_id == f"button.ficus_{key}"
        entity = registry.async_get(entity_id)
        assert entity is not None
        assert entity.device_id == device.id
        assert entity.config_subentry_id == subentry_id
        assert entity.translation_key == key


@pytest.mark.parametrize(
    ("key", "last_key"), [("water", "last_watered"), ("feed", "last_fed")]
)
async def test_press_logs_care_now(
    hass: HomeAssistant,
    plant_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    key: str,
    last_key: str,
) -> None:
    """Pressing a button logs that care at the current time."""
    now = dt_util.utcnow().replace(microsecond=0)
    freezer.move_to(now)

    await _press(hass, key)

    state = hass.states.get(f"sensor.ficus_{last_key}")
    assert state is not None
    assert dt_util.parse_datetime(state.state) == now


@pytest.mark.parametrize(
    ("kind", "key", "needs_key"),
    [
        (CareKind.WATERED, "water", "needs_water"),
        (CareKind.FED, "feed", "needs_feeding"),
    ],
)
async def test_press_clears_the_need(
    hass: HomeAssistant,
    plant_entry: MockConfigEntry,
    kind: CareKind,
    key: str,
    needs_key: str,
) -> None:
    """An overdue plant no longer needs that care once the button is pressed."""
    (subentry_id,) = plant_entry.subentries
    await plant_entry.runtime_data.coordinator.async_log_care(
        CareEvent(
            plant_id=subentry_id, kind=kind, at=dt_util.utcnow() - timedelta(days=200)
        )
    )
    await hass.async_block_till_done()
    needs = f"binary_sensor.ficus_{needs_key}"
    assert (state := hass.states.get(needs)) is not None
    assert state.state == STATE_ON

    await _press(hass, key)

    assert (state := hass.states.get(needs)) is not None
    assert state.state == STATE_OFF
