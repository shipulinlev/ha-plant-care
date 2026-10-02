"""Tests for the coordinator: inputs per plant, refresh triggers, clean unload."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from http import HTTPStatus
from typing import Any
from unittest.mock import patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_NAME,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.plant_care.const import (
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_SPECIES_PID,
    CONF_WATERING_INTERVAL,
    CONF_WEATHER_ENTITY,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from custom_components.plant_care.core.engine import CareEngine
from custom_components.plant_care.core.models import (
    CareEvent,
    CareKind,
    CarePlan,
    ClimateStatus,
)
from custom_components.plant_care.openplantbook import BASE_URL

INDOOR = {
    CONF_NAME: "Ficus",
    CONF_LOCATION_TYPE: "indoor",
    CONF_WATERING_INTERVAL: 7,
    CONF_FEEDING_INTERVAL: 30,
    "min_temp": 18.0,
    "max_temp": 24.0,
}
OUTDOOR = {**INDOOR, CONF_NAME: "Rose", CONF_LOCATION_TYPE: "outdoor"}


@pytest.fixture
def kitchen(hass: HomeAssistant) -> str:
    return ar.async_get(hass).async_create("Kitchen").id


@pytest.fixture
def hall(hass: HomeAssistant) -> str:
    return ar.async_get(hass).async_create("Hall").id


@pytest.fixture
def plan_calls() -> Iterator[list[str]]:
    """Plant ids the engine planned, in order (wraps the real engine)."""
    calls: list[str] = []
    original = CareEngine.plan

    def spy(self: CareEngine, **kwargs: Any) -> CarePlan:
        calls.append(kwargs["plant"].plant_id)
        return original(self, **kwargs)

    with patch.object(CareEngine, "plan", spy):
        yield calls


def _hub(
    hass: HomeAssistant, *plants: dict[str, Any], **hub_data: Any
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CLIENT_ID: "id", CONF_CLIENT_SECRET: "secret", **hub_data},
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


def _plan(entry: MockConfigEntry, subentry_id: str) -> CarePlan:
    plan: CarePlan = entry.runtime_data.coordinator.data[subentry_id]
    return plan


def _move_plant(
    hass: HomeAssistant, entry: MockConfigEntry, subentry_id: str, area_id: str
) -> None:
    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, subentry_id), entry.entry_id
    )
    assert device is not None
    registry.async_update_device(device.id, area_id=area_id)


def _temp_sensor(hass: HomeAssistant, name: str, area_id: str | None) -> str:
    source = MockConfigEntry(domain="test")
    source.add_to_hass(hass)
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "sensor",
        "test",
        name,
        config_entry=source,
        original_device_class=SensorDeviceClass.TEMPERATURE,
        suggested_object_id=name,
    )
    if area_id is not None:
        registry.async_update_entity(entity.entity_id, area_id=area_id)
    return entity.entity_id


def _temperature(hass: HomeAssistant, entity_id: str, value: float) -> None:
    hass.states.async_set(
        entity_id, str(value), {"unit_of_measurement": UnitOfTemperature.CELSIUS}
    )


async def _water(entry: MockConfigEntry, subentry_id: str, days_ago: float) -> None:
    await entry.runtime_data.coordinator.async_log_care(
        CareEvent(
            plant_id=subentry_id,
            kind=CareKind.WATERED,
            at=dt_util.utcnow() - timedelta(days=days_ago),
        )
    )


async def test_every_plant_gets_a_plan(hass: HomeAssistant) -> None:
    """Setup computes a plan per plant; without history nothing is scheduled."""
    entry = _hub(hass, INDOOR, OUTDOOR)

    await _setup(hass, entry)

    for subentry_id in entry.subentries:
        plan = _plan(entry, subentry_id)
        assert plan.next_watering is None
        assert plan.climate_status is ClimateStatus.UNKNOWN


async def test_logging_care_refreshes_the_plan(hass: HomeAssistant) -> None:
    """A logged watering is stored and shows up in the plan at once."""
    entry = _hub(hass, INDOOR)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)

    await _water(entry, subentry_id, days_ago=1)

    plan = _plan(entry, subentry_id)
    assert plan.last_watered is not None
    assert plan.next_watering == plan.last_watered + timedelta(days=7)
    assert entry.runtime_data.care_log.plant_ids() == {subentry_id}


async def test_indoor_plan_uses_area_sensors_and_overrides(
    hass: HomeAssistant, kitchen: str
) -> None:
    """A hot room (above the overridden range) shortens the interval."""
    sensor = _temp_sensor(hass, "kitchen_temp", kitchen)
    _temperature(hass, sensor, 30)
    entry = _hub(hass, INDOOR)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)
    _move_plant(hass, entry, subentry_id, kitchen)
    await hass.async_block_till_done()

    await _water(entry, subentry_id, days_ago=1)

    plan = _plan(entry, subentry_id)
    assert plan.climate_status is ClimateStatus.OUT_OF_RANGE
    assert plan.last_watered is not None
    assert plan.next_watering is not None
    assert plan.next_watering < plan.last_watered + timedelta(days=7)


async def test_sensor_state_change_refreshes(hass: HomeAssistant, kitchen: str) -> None:
    """A new reading from a source sensor recomputes the plan."""
    sensor = _temp_sensor(hass, "kitchen_temp", kitchen)
    _temperature(hass, sensor, 21)
    entry = _hub(hass, INDOOR)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)
    _move_plant(hass, entry, subentry_id, kitchen)
    await hass.async_block_till_done()
    assert _plan(entry, subentry_id).climate_status is ClimateStatus.OK

    _temperature(hass, sensor, 30)
    await hass.async_block_till_done()

    assert _plan(entry, subentry_id).climate_status is ClimateStatus.OUT_OF_RANGE


async def test_moving_the_plant_switches_sensors(
    hass: HomeAssistant, kitchen: str, hall: str
) -> None:
    """Changing the device area re-resolves the climate sources."""
    _temperature(hass, _temp_sensor(hass, "kitchen_temp", kitchen), 30)
    _temperature(hass, _temp_sensor(hass, "hall_temp", hall), 21)
    entry = _hub(hass, INDOOR)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)

    _move_plant(hass, entry, subentry_id, kitchen)
    await hass.async_block_till_done()
    assert _plan(entry, subentry_id).climate_status is ClimateStatus.OUT_OF_RANGE

    _move_plant(hass, entry, subentry_id, hall)
    await hass.async_block_till_done()
    assert _plan(entry, subentry_id).climate_status is ClimateStatus.OK


async def test_sensor_added_to_area_is_picked_up(
    hass: HomeAssistant, kitchen: str
) -> None:
    """A sensor assigned to the plant's area later starts counting."""
    entry = _hub(hass, INDOOR)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)
    _move_plant(hass, entry, subentry_id, kitchen)
    sensor = _temp_sensor(hass, "late_temp", None)
    _temperature(hass, sensor, 30)
    await hass.async_block_till_done()
    assert _plan(entry, subentry_id).climate_status is ClimateStatus.UNKNOWN

    er.async_get(hass).async_update_entity(sensor, area_id=kitchen)
    await hass.async_block_till_done()

    assert _plan(entry, subentry_id).climate_status is ClimateStatus.OUT_OF_RANGE


async def test_outdoor_plan_uses_hub_weather_and_rain(hass: HomeAssistant) -> None:
    """Outdoor plants read the hub's weather entity and its rain forecast."""
    hass.states.async_set(
        "weather.home",
        "rainy",
        {"temperature": 21, "temperature_unit": "°C", "precipitation_unit": "mm"},
    )
    today = dt_util.start_of_local_day()

    async def forecasts(call: ServiceCall) -> dict[str, Any]:
        return {
            "weather.home": {
                "forecast": [
                    {
                        "datetime": (today + timedelta(days=2)).isoformat(),
                        "precipitation": 12.0,
                    }
                ]
            }
        }

    hass.services.async_register(
        "weather", "get_forecasts", forecasts, supports_response=SupportsResponse.ONLY
    )
    entry = _hub(hass, OUTDOOR, **{CONF_WEATHER_ENTITY: "weather.home"})
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)

    await _water(entry, subentry_id, days_ago=1)

    plan = _plan(entry, subentry_id)
    assert plan.climate_status is ClimateStatus.OK
    # Forecast rain in two days counts as a watering and restarts the interval.
    assert plan.next_watering == dt_util.as_utc(today + timedelta(days=2)) + timedelta(
        days=7
    )


async def test_species_profile_is_fetched_and_cached(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A plant's species profile is fetched once and kept in the cache."""
    aioclient_mock.post(
        f"{BASE_URL}/token/", json={"access_token": "t", "expires_in": 3600}
    )
    aioclient_mock.get(
        f"{BASE_URL}/plant/detail/ficus/", json={"min_temp": 10, "max_temp": 30}
    )
    plant = {**INDOOR, CONF_SPECIES_PID: "ficus"}
    del plant["min_temp"], plant["max_temp"]
    entry = _hub(hass, plant)
    await _setup(hass, entry)

    await entry.runtime_data.coordinator.async_refresh()

    cached = entry.runtime_data.coordinator.profile_cache.get("ficus")
    assert cached is not None
    assert cached.min_temp == 10
    detail_calls = [c for c in aioclient_mock.mock_calls if "detail" in str(c[1])]
    assert len(detail_calls) == 1


async def test_unreachable_openplantbook_is_not_fatal(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Without OpenPlantbook the hub still loads and retries only later."""
    aioclient_mock.post(f"{BASE_URL}/token/", status=HTTPStatus.SERVICE_UNAVAILABLE)
    entry = _hub(hass, {**INDOOR, CONF_SPECIES_PID: "ficus"})
    (subentry_id,) = entry.subentries

    await _setup(hass, entry)
    await entry.runtime_data.coordinator.async_refresh()

    assert _plan(entry, subentry_id) is not None
    assert aioclient_mock.call_count == 1


async def test_unload_stops_all_triggers(
    hass: HomeAssistant, kitchen: str, plan_calls: list[str]
) -> None:
    """After unload neither states nor registry changes reach the coordinator."""
    sensor = _temp_sensor(hass, "kitchen_temp", kitchen)
    _temperature(hass, sensor, 21)
    entry = _hub(hass, INDOOR)
    (subentry_id,) = entry.subentries
    await _setup(hass, entry)
    _move_plant(hass, entry, subentry_id, kitchen)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    calls_before = len(plan_calls)

    _temperature(hass, sensor, 30)
    er.async_get(hass).async_update_entity(sensor, area_id=None)
    await hass.async_block_till_done()

    assert len(plan_calls) == calls_before


async def test_unload_releases_state_subscriptions(
    hass: HomeAssistant, kitchen: str
) -> None:
    """Every state subscription the coordinator opened is closed on unload."""
    open_subscriptions = 0
    real_track = async_track_state_change_event

    def counting_track(*args: Any, **kwargs: Any) -> Callable[[], None]:
        nonlocal open_subscriptions
        unsubscribe = real_track(*args, **kwargs)
        open_subscriptions += 1

        def counted_unsubscribe() -> None:
            nonlocal open_subscriptions
            open_subscriptions -= 1
            unsubscribe()

        return counted_unsubscribe

    _temperature(hass, _temp_sensor(hass, "kitchen_temp", kitchen), 21)
    entry = _hub(hass, INDOOR)
    (subentry_id,) = entry.subentries
    with patch(
        "custom_components.plant_care.coordinator.async_track_state_change_event",
        counting_track,
    ):
        await _setup(hass, entry)
        _move_plant(hass, entry, subentry_id, kitchen)
        await hass.async_block_till_done()
        assert open_subscriptions == 1

        assert await hass.config_entries.async_unload(entry.entry_id)

    assert open_subscriptions == 0
