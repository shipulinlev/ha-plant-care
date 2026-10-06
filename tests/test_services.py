"""Tests for the plant care actions."""

from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar, device_registry as dr
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.plant_care.const import (
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.plant_care.core.models import CareKind, SpeciesProfile
from custom_components.plant_care.openplantbook import BASE_URL


def _device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    (subentry_id,) = entry.subentries
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), entry.entry_id
    )
    assert device is not None
    return device.id


async def _call(hass: HomeAssistant, service: str, data: dict[str, Any]) -> None:
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await hass.async_block_till_done()


def _logged(entry: MockConfigEntry, kind: CareKind) -> list[datetime]:
    (subentry_id,) = entry.subentries
    return [
        event.at
        for event in entry.runtime_data.care_log.events(subentry_id)
        if event.kind == kind
    ]


async def _raises(
    hass: HomeAssistant, service: str, data: dict[str, Any], key: str
) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, service, data)
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == key


@pytest.mark.parametrize(
    ("service", "kind"), [("water", CareKind.WATERED), ("feed", CareKind.FED)]
)
async def test_care_is_logged_now(
    hass: HomeAssistant,
    plant_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    service: str,
    kind: CareKind,
) -> None:
    """Without `when`, the care is logged at the current time."""
    now = dt_util.utcnow().replace(microsecond=0)
    freezer.move_to(now)

    await _call(hass, service, {"device_id": _device_id(hass, plant_entry)})

    assert _logged(plant_entry, kind) == [now]


async def test_care_can_be_backdated(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """`when` logs the care in the past; a time without zone is local time."""
    device_id = _device_id(hass, plant_entry)
    when = (dt_util.now() - timedelta(days=2)).replace(microsecond=0)

    await _call(
        hass,
        "water",
        {"device_id": device_id, "when": when.replace(tzinfo=None).isoformat()},
    )

    assert _logged(plant_entry, CareKind.WATERED) == [dt_util.as_utc(when)]


async def test_future_care_is_rejected(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """Care cannot be logged ahead of time."""
    when = dt_util.utcnow() + timedelta(hours=1)

    await _raises(
        hass,
        "feed",
        {"device_id": _device_id(hass, plant_entry), "when": when.isoformat()},
        "when_in_future",
    )
    assert _logged(plant_entry, CareKind.FED) == []


async def test_unknown_device_is_rejected(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """A device id that is not a plant is a clear error."""
    other = MockConfigEntry(
        domain="other",
        subentries_data=[
            ConfigSubentryData(
                data={}, subentry_type=SUBENTRY_TYPE_PLANT, title="x", unique_id=None
            )
        ],
    )
    other.add_to_hass(hass)
    (other_subentry_id,) = other.subentries
    devices = dr.async_get(hass)
    foreign = devices.async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("other", "x")}
    )
    foreign_plant = devices.async_get_or_create(
        config_entry_id=other.entry_id,
        config_subentry_id=other_subentry_id,
        identifiers={("other", "y")},
    )

    for device_id in ("missing", foreign.id, foreign_plant.id):
        await _raises(hass, "water", {"device_id": device_id}, "plant_not_found")


async def test_unloaded_hub_is_rejected(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """Actions need the hub loaded."""
    device_id = _device_id(hass, plant_entry)
    assert await hass.config_entries.async_unload(plant_entry.entry_id)
    await hass.async_block_till_done()

    await _raises(hass, "water", {"device_id": device_id}, "hub_not_loaded")


async def test_move_sets_the_device_area(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """`move` puts the plant's device into the area."""
    kitchen = ar.async_get(hass).async_create("Kitchen").id
    device_id = _device_id(hass, plant_entry)

    await _call(hass, "move", {"device_id": device_id, "area_id": kitchen})

    device = dr.async_get(hass).async_get(device_id)
    assert device is not None
    assert device.area_id == kitchen


async def test_move_to_unknown_area_is_rejected(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """An area that does not exist is a clear error."""
    device_id = _device_id(hass, plant_entry)

    await _raises(
        hass, "move", {"device_id": device_id, "area_id": "nowhere"}, "area_not_found"
    )


def _mock_openplantbook(aioclient_mock: AiohttpClientMocker, min_temp: float) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.post(
        f"{BASE_URL}/token/", json={"access_token": "t", "expires_in": 3600}
    )
    aioclient_mock.get(f"{BASE_URL}/plant/detail/ficus/", json={"min_temp": min_temp})


def _cached_min_temp(entry: MockConfigEntry) -> float | None:
    profile: SpeciesProfile | None = entry.runtime_data.coordinator.profile_cache.get(
        "ficus"
    )
    assert profile is not None
    return profile.min_temp


async def test_refresh_species_refetches_the_profile(
    hass: HomeAssistant,
    species_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A fresh cached profile is fetched again on request."""
    assert _cached_min_temp(species_entry) == 10
    _mock_openplantbook(aioclient_mock, min_temp=12)

    await _call(hass, "refresh_species", {"device_id": _device_id(hass, species_entry)})

    assert _cached_min_temp(species_entry) == 12


async def test_refresh_species_skips_the_retry_pause(
    hass: HomeAssistant,
    species_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """After a failed fetch, a refresh request still tries again at once."""
    coordinator = species_entry.runtime_data.coordinator
    await coordinator.profile_cache.async_remove("ficus")
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE_URL}/plant/detail/ficus/", status=HTTPStatus.SERVICE_UNAVAILABLE
    )
    await coordinator.async_refresh()
    assert coordinator.profile_cache.get("ficus") is None
    _mock_openplantbook(aioclient_mock, min_temp=12)

    await _call(hass, "refresh_species", {"device_id": _device_id(hass, species_entry)})

    assert _cached_min_temp(species_entry) == 12


async def test_refresh_species_needs_a_species(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """A plant without a species has nothing to refresh."""
    await _raises(
        hass,
        "refresh_species",
        {"device_id": _device_id(hass, plant_entry)},
        "no_species",
    )
