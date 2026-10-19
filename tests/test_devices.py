"""Tests for plant devices: creation, area handoff, rename, removal."""

from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import SOURCE_USER, ConfigSubentryData
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.const import (
    CONF_AREA_ID,
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_WATERING_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.plant_care.core.models import CareEvent, CareKind

PLANT = {
    CONF_NAME: "Ficus",
    CONF_LOCATION_TYPE: "indoor",
    CONF_WATERING_INTERVAL: 7,
    CONF_FEEDING_INTERVAL: 30,
}
DETAILS = {key: PLANT[key] for key in PLANT if key != CONF_NAME}


def _hub(hass: HomeAssistant, *plants: dict[str, Any]) -> MockConfigEntry:
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
            for plant in plants
        ],
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _plant_device(
    hass: HomeAssistant, entry: MockConfigEntry, subentry_id: str
) -> dr.DeviceEntry | None:
    return dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), entry.entry_id
    )


@pytest.fixture
def kitchen(hass: HomeAssistant) -> ar.AreaEntry:
    return ar.async_get(hass).async_create("Kitchen")


async def test_setup_creates_one_device_per_plant(hass: HomeAssistant) -> None:
    """Each plant gets its own device, bound to its subentry."""
    entry = _hub(hass, PLANT, {**PLANT, CONF_NAME: "Monstera"})

    await _setup(hass, entry)

    for subentry_id, subentry in entry.subentries.items():
        device = _plant_device(hass, entry, subentry_id)
        assert device is not None
        assert device.name == subentry.title
        assert device.config_entry_id == entry.entry_id
        assert device.config_subentry_id == subentry_id
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 2


async def test_pending_area_is_applied_and_removed(
    hass: HomeAssistant, kitchen: ar.AreaEntry
) -> None:
    """The one-time area handoff lands on the device and leaves the data."""
    entry = _hub(hass, {**PLANT, CONF_AREA_ID: kitchen.id})
    (subentry_id,) = entry.subentries

    await _setup(hass, entry)

    device = _plant_device(hass, entry, subentry_id)
    assert device is not None
    assert device.area_id == kitchen.id
    assert dict(entry.subentries[subentry_id].data) == PLANT


async def test_unknown_area_is_dropped(hass: HomeAssistant) -> None:
    """An area deleted before setup is ignored and the key still removed."""
    entry = _hub(hass, {**PLANT, CONF_AREA_ID: "gone"})
    (subentry_id,) = entry.subentries

    await _setup(hass, entry)

    device = _plant_device(hass, entry, subentry_id)
    assert device is not None
    assert device.area_id is None
    assert CONF_AREA_ID not in entry.subentries[subentry_id].data


async def test_device_area_is_left_alone_after_handoff(
    hass: HomeAssistant, kitchen: ar.AreaEntry
) -> None:
    """A reload keeps an area the user set on the device."""
    entry = _hub(hass, PLANT)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)
    device = _plant_device(hass, entry, subentry_id)
    assert device is not None
    dr.async_get(hass).async_update_device(device.id, area_id=kitchen.id)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    device = _plant_device(hass, entry, subentry_id)
    assert device is not None
    assert device.area_id == kitchen.id


async def test_added_plant_gets_device_with_area(
    hass: HomeAssistant, kitchen: ar.AreaEntry
) -> None:
    """Adding a plant to a running hub creates its device right away."""
    entry = _hub(hass)
    await _setup(hass, entry)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_PLANT), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Ficus"}
    )
    await hass.config_entries.subentries.async_configure(
        result["flow_id"], {**DETAILS, CONF_AREA_ID: kitchen.id}
    )
    await hass.async_block_till_done()

    (subentry_id,) = entry.subentries
    device = _plant_device(hass, entry, subentry_id)
    assert device is not None
    assert device.area_id == kitchen.id
    assert CONF_AREA_ID not in entry.subentries[subentry_id].data


async def test_renamed_plant_renames_device(hass: HomeAssistant) -> None:
    """Editing a plant on a running hub updates its device name."""
    entry = _hub(hass, PLANT)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)

    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_NAME: "Weeping fig", **DETAILS}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    device = _plant_device(hass, entry, subentry_id)
    assert device is not None
    assert device.name == "Weeping fig"


async def test_removed_plant_loses_device_and_history(hass: HomeAssistant) -> None:
    """Deleting a plant removes its device and its care history."""
    entry = _hub(hass, PLANT, {**PLANT, CONF_NAME: "Monstera"})
    await _setup(hass, entry)
    removed_id, kept_id = entry.subentries
    for plant_id in (removed_id, kept_id):
        await entry.runtime_data.care_log.async_add(
            CareEvent(
                plant_id=plant_id,
                kind=CareKind.WATERED,
                at=datetime(2026, 9, 1, tzinfo=UTC),
            )
        )

    assert hass.config_entries.async_remove_subentry(entry, removed_id)
    await hass.async_block_till_done()

    assert _plant_device(hass, entry, removed_id) is None
    assert _plant_device(hass, entry, kept_id) is not None
    assert entry.runtime_data.care_log.plant_ids() == {kept_id}


async def test_unload_removes_update_listener(hass: HomeAssistant) -> None:
    """Unloading the hub leaves no listener behind."""
    entry = _hub(hass, PLANT)
    await _setup(hass, entry)
    assert entry.update_listeners

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert not entry.update_listeners
