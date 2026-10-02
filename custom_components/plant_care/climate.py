"""Climate sources of a plant (not the HA `climate` platform).

Indoor plants read the temperature and humidity sensors of their area;
outdoor plants read a weather entity (rain comes from `rain.py`).
"""

from dataclasses import dataclass
import math
from statistics import median

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.weather.const import (
    ATTR_WEATHER_HUMIDITY,
    ATTR_WEATHER_TEMPERATURE,
    ATTR_WEATHER_TEMPERATURE_UNIT,
)
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util.unit_conversion import TemperatureConverter

from .core.models import ClimateReading

TEMP = SensorDeviceClass.TEMPERATURE.value
HUMID = SensorDeviceClass.HUMIDITY.value


@dataclass(frozen=True, slots=True, kw_only=True)
class IndoorSources:
    """Sensor entity ids of an area, sorted, per measured quantity."""

    temperature: tuple[str, ...] = ()
    humidity: tuple[str, ...] = ()

    @property
    def entity_ids(self) -> tuple[str, ...]:
        """Every source, e.g. to subscribe to state changes."""
        return self.temperature + self.humidity


@callback
def async_indoor_sources(hass: HomeAssistant, area_id: str | None) -> IndoorSources:
    """Temperature and humidity sensors in an area.

    An entity's own area wins; without one, its device's area counts.
    """
    if area_id is None:
        return IndoorSources()
    entity_registry = er.async_get(hass)
    entries = [
        entry
        for entry in er.async_entries_for_area(entity_registry, area_id)
        if entry.domain == "sensor"
    ]
    for device in dr.async_entries_for_area(dr.async_get(hass), area_id):
        entries.extend(
            entry
            for entry in er.async_entries_for_device(entity_registry, device.id)
            if entry.domain == "sensor" and entry.area_id is None
        )
    by_class: dict[str, list[str]] = {TEMP: [], HUMID: []}
    for entry in entries:
        device_class = entry.device_class or entry.original_device_class
        if entry.disabled_by is None and device_class in by_class:
            by_class[device_class].append(entry.entity_id)
    return IndoorSources(
        temperature=tuple(sorted(by_class[TEMP])),
        humidity=tuple(sorted(by_class[HUMID])),
    )


@callback
def read_indoor(
    hass: HomeAssistant, sources: IndoorSources, soil_moisture_entity: str | None
) -> ClimateReading:
    """Current conditions: medians of the area sensors, temperature in °C."""
    temperatures = [
        value
        for entity_id in sources.temperature
        if (value := _celsius(hass, entity_id)) is not None
    ]
    humidities = [
        value
        for entity_id in sources.humidity
        if (value := _number(hass, entity_id)) is not None
    ]
    return ClimateReading(
        temperature=median(temperatures) if temperatures else None,
        humidity=median(humidities) if humidities else None,
        soil_moisture=(
            _number(hass, soil_moisture_entity) if soil_moisture_entity else None
        ),
    )


@callback
def read_outdoor(
    hass: HomeAssistant, weather_entity: str | None, soil_moisture_entity: str | None
) -> ClimateReading:
    """Current conditions from a weather entity, temperature in °C."""
    soil = _number(hass, soil_moisture_entity) if soil_moisture_entity else None
    state = hass.states.get(weather_entity) if weather_entity else None
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return ClimateReading(soil_moisture=soil)
    temperature = _finite(state.attributes.get(ATTR_WEATHER_TEMPERATURE))
    if temperature is not None:
        temperature = _to_celsius(
            temperature,
            state.attributes.get(
                ATTR_WEATHER_TEMPERATURE_UNIT, hass.config.units.temperature_unit
            ),
        )
    return ClimateReading(
        temperature=temperature,
        humidity=_finite(state.attributes.get(ATTR_WEATHER_HUMIDITY)),
        soil_moisture=soil,
    )


def _number(hass: HomeAssistant, entity_id: str) -> float | None:
    """The numeric state; None when missing, unavailable, unknown or not a number."""
    state = hass.states.get(entity_id)
    return _finite(state.state) if state is not None else None


def _celsius(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    value = _finite(state.state) if state is not None else None
    if state is None or value is None:
        return None
    return _to_celsius(
        value,
        state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature.CELSIUS),
    )


def _to_celsius(value: float, unit: str) -> float | None:
    try:
        return TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)
    except HomeAssistantError:
        return None


def _finite(raw: object) -> float | None:
    """A finite float, or None for anything else (unavailable, text, nan)."""
    if isinstance(raw, bool) or not isinstance(raw, str | int | float):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None
