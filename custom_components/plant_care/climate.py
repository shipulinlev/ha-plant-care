"""Climate sources of a plant (not the HA `climate` platform).

Indoor plants read the temperature and humidity sensors of their area.
"""

from dataclasses import dataclass
import math
from statistics import median

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature
from homeassistant.core import HomeAssistant, State, callback
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


def _number(hass: HomeAssistant, entity_id: str) -> float | None:
    """The numeric state; None when missing, unavailable, unknown or not a number."""
    return _value(hass.states.get(entity_id))


def _celsius(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    value = _value(state)
    if state is None or value is None:
        return None
    unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature.CELSIUS)
    try:
        return TemperatureConverter.convert(value, unit, UnitOfTemperature.CELSIUS)
    except HomeAssistantError:
        return None


def _value(state: State | None) -> float | None:
    if state is None:
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value if math.isfinite(value) else None
