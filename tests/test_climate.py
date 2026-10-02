"""Tests for indoor climate sources: area sensors and their readings."""

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_care.climate import (
    IndoorSources,
    async_indoor_sources,
    read_indoor,
)
from custom_components.plant_care.core.models import ClimateReading

TEMP = SensorDeviceClass.TEMPERATURE
HUMID = SensorDeviceClass.HUMIDITY


@pytest.fixture
def source_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Config entry owning the test sensors and devices."""
    entry = MockConfigEntry(domain="test")
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def kitchen(hass: HomeAssistant) -> str:
    return ar.async_get(hass).async_create("Kitchen").id


@pytest.fixture
def hall(hass: HomeAssistant) -> str:
    return ar.async_get(hass).async_create("Hall").id


def _sensor(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    name: str,
    device_class: SensorDeviceClass | None,
    *,
    area_id: str | None = None,
    device_area_id: str | None = None,
    disabled: bool = False,
) -> str:
    device_id = None
    if device_area_id is not None:
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("test", name)}
        )
        dr.async_get(hass).async_update_device(device.id, area_id=device_area_id)
        device_id = device.id
    registry = er.async_get(hass)
    entity = registry.async_get_or_create(
        "sensor",
        "test",
        name,
        config_entry=entry,
        device_id=device_id,
        original_device_class=device_class,
        suggested_object_id=name,
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None,
    )
    if area_id is not None:
        registry.async_update_entity(entity.entity_id, area_id=area_id)
    return entity.entity_id


def _state(
    hass: HomeAssistant, entity_id: str, value: str, unit: str = PERCENTAGE
) -> None:
    hass.states.async_set(entity_id, value, {"unit_of_measurement": unit})


async def test_finds_sensors_by_entity_or_device_area(
    hass: HomeAssistant, source_entry: MockConfigEntry, kitchen: str, hall: str
) -> None:
    """A sensor belongs to an area directly or through its device."""
    direct = _sensor(hass, source_entry, "t_direct", TEMP, area_id=kitchen)
    via_device = _sensor(hass, source_entry, "t_device", TEMP, device_area_id=kitchen)
    humidity = _sensor(hass, source_entry, "h_kitchen", HUMID, area_id=kitchen)
    _sensor(hass, source_entry, "t_hall", TEMP, area_id=hall)
    # The entity's own area wins over its device's area.
    _sensor(hass, source_entry, "t_moved", TEMP, area_id=hall, device_area_id=kitchen)
    _sensor(hass, source_entry, "power", None, area_id=kitchen)
    _sensor(hass, source_entry, "t_disabled", TEMP, area_id=kitchen, disabled=True)

    sources = async_indoor_sources(hass, kitchen)

    assert sources == IndoorSources(
        temperature=tuple(sorted((direct, via_device))), humidity=(humidity,)
    )
    assert set(sources.entity_ids) == {direct, via_device, humidity}


async def test_device_class_override_counts(
    hass: HomeAssistant, source_entry: MockConfigEntry, kitchen: str
) -> None:
    """A device class the user set on the entity wins over the original one."""
    entity_id = _sensor(hass, source_entry, "generic", None, area_id=kitchen)
    er.async_get(hass).async_update_entity(entity_id, device_class=HUMID)

    assert async_indoor_sources(hass, kitchen).humidity == (entity_id,)


async def test_no_area_means_no_sources(hass: HomeAssistant) -> None:
    """A plant without an area has no indoor sensors."""
    assert async_indoor_sources(hass, None) == IndoorSources()


async def test_reading_takes_medians(
    hass: HomeAssistant, source_entry: MockConfigEntry, kitchen: str
) -> None:
    """Several sensors are combined by median."""
    temps = [
        _sensor(hass, source_entry, f"t{i}", TEMP, area_id=kitchen) for i in range(3)
    ]
    humid = [
        _sensor(hass, source_entry, f"h{i}", HUMID, area_id=kitchen) for i in range(2)
    ]
    for entity_id, value in zip(temps, ("20", "30", "21"), strict=True):
        _state(hass, entity_id, value, UnitOfTemperature.CELSIUS)
    for entity_id, value in zip(humid, ("40", "50"), strict=True):
        _state(hass, entity_id, value)

    reading = read_indoor(hass, async_indoor_sources(hass, kitchen), None)

    assert reading == ClimateReading(temperature=21.0, humidity=45.0)


async def test_reading_skips_unusable_states(
    hass: HomeAssistant, source_entry: MockConfigEntry, kitchen: str
) -> None:
    """Unavailable, unknown and non-numeric states are ignored."""
    temps = [
        _sensor(hass, source_entry, f"t{i}", TEMP, area_id=kitchen) for i in range(4)
    ]
    humidity = _sensor(hass, source_entry, "h", HUMID, area_id=kitchen)
    for entity_id, value in zip(
        temps, (STATE_UNAVAILABLE, STATE_UNKNOWN, "warm", "22.5"), strict=True
    ):
        _state(hass, entity_id, value, UnitOfTemperature.CELSIUS)
    _state(hass, humidity, STATE_UNAVAILABLE)

    reading = read_indoor(hass, async_indoor_sources(hass, kitchen), None)

    assert reading == ClimateReading(temperature=22.5, humidity=None)


async def test_fahrenheit_is_converted(
    hass: HomeAssistant, source_entry: MockConfigEntry, kitchen: str
) -> None:
    """Species ranges are in °C, so °F readings are converted."""
    entity_id = _sensor(hass, source_entry, "t", TEMP, area_id=kitchen)
    _state(hass, entity_id, "77", UnitOfTemperature.FAHRENHEIT)

    reading = read_indoor(hass, async_indoor_sources(hass, kitchen), None)

    assert reading.temperature == pytest.approx(25.0)


async def test_soil_moisture_sensor_is_read(hass: HomeAssistant) -> None:
    """The plant's own soil sensor is read wherever it is."""
    _state(hass, "sensor.pot", "35")

    assert read_indoor(hass, IndoorSources(), "sensor.pot") == ClimateReading(
        soil_moisture=35.0
    )


async def test_missing_soil_moisture_sensor_reads_none(hass: HomeAssistant) -> None:
    """A soil sensor that is gone or unavailable gives no reading."""
    _state(hass, "sensor.pot", STATE_UNAVAILABLE)

    assert read_indoor(hass, IndoorSources(), "sensor.pot").soil_moisture is None
    assert read_indoor(hass, IndoorSources(), "sensor.gone").soil_moisture is None
