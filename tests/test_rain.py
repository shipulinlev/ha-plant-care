"""Tests for outdoor readings and the rain tracker."""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest

from custom_components.plant_care.climate import read_outdoor
from custom_components.plant_care.core.models import ClimateReading, Precipitation
from custom_components.plant_care.rain import (
    RAIN_FORECAST_TTL,
    RAIN_HISTORY_DAYS,
    RainTracker,
)

WEATHER = "weather.garden"
Forecasts = dict[str, list[dict[str, Any]] | Exception]


def _day(offset: int) -> date:
    return dt_util.now().date() + timedelta(days=offset)


def _local(day: date, hour: int = 0) -> str:
    return (dt_util.start_of_local_day(day) + timedelta(hours=hour)).isoformat()


def _rain(day: date, amount_mm: float) -> Precipitation:
    return Precipitation(
        at=dt_util.as_utc(dt_util.start_of_local_day(day)), amount_mm=amount_mm
    )


@pytest.fixture
def forecasts(hass: HomeAssistant) -> Forecasts:
    """Fake weather.get_forecasts: forecast lists (or errors) per type."""
    data: Forecasts = {}
    hass.states.async_set(WEATHER, "rainy", {"precipitation_unit": "mm"})

    async def handle(call: ServiceCall) -> dict[str, Any]:
        result = data.get(call.data["type"])
        if result is None:
            raise HomeAssistantError("forecast type not supported")
        if isinstance(result, Exception):
            raise result
        entity_ids = call.data["entity_id"]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        return {entity_id: {"forecast": result} for entity_id in entity_ids}

    hass.services.async_register(
        "weather", "get_forecasts", handle, supports_response=SupportsResponse.ONLY
    )
    return data


def _calls(hass: HomeAssistant) -> Callable[[], int]:
    count = 0

    def listener(event: Any) -> None:
        nonlocal count
        if event.data["service"] == "get_forecasts":
            count += 1

    hass.bus.async_listen("call_service", listener)
    return lambda: count


async def test_daily_forecast_gives_rain_per_day(
    hass: HomeAssistant, forecasts: Forecasts
) -> None:
    """Each daily entry becomes one precipitation at the start of its local day."""
    forecasts["daily"] = [
        {"datetime": _local(_day(0), 12), "precipitation": 2.0},
        {"datetime": _local(_day(1), 12), "precipitation": 7.5},
        {"datetime": _local(_day(2), 12), "precipitation": None},
    ]
    tracker = RainTracker(hass)

    await tracker.async_refresh(WEATHER)

    assert tracker.precipitation(WEATHER) == (
        _rain(_day(0), 2.0),
        _rain(_day(1), 7.5),
    )


async def test_hourly_forecast_is_summed_per_day(
    hass: HomeAssistant, forecasts: Forecasts
) -> None:
    """Without a daily forecast, hourly entries are summed per local day."""
    forecasts["hourly"] = [
        {"datetime": _local(_day(1), 1), "precipitation": 1.0},
        {"datetime": _local(_day(1), 2), "precipitation": 2.5},
        {"datetime": _local(_day(2), 1), "precipitation": 4.0},
    ]
    tracker = RainTracker(hass)

    await tracker.async_refresh(WEATHER)

    assert tracker.precipitation(WEATHER) == (
        _rain(_day(1), 3.5),
        _rain(_day(2), 4.0),
    )


async def test_inches_are_converted(hass: HomeAssistant, forecasts: Forecasts) -> None:
    """Forecasts in inches become millimetres."""
    hass.states.async_set(WEATHER, "rainy", {"precipitation_unit": "in"})
    forecasts["daily"] = [{"datetime": _local(_day(1)), "precipitation": 1.0}]
    tracker = RainTracker(hass)

    await tracker.async_refresh(WEATHER)

    (rain,) = tracker.precipitation(WEATHER)
    assert rain.amount_mm == pytest.approx(25.4)


async def test_forecast_is_fetched_once_per_ttl(
    hass: HomeAssistant, forecasts: Forecasts, freezer: FrozenDateTimeFactory
) -> None:
    """Refreshes within the TTL are served from the cache."""
    forecasts["daily"] = [{"datetime": _local(_day(1)), "precipitation": 1.0}]
    calls = _calls(hass)
    tracker = RainTracker(hass)

    await tracker.async_refresh(WEATHER)
    await tracker.async_refresh(WEATHER)
    await hass.async_block_till_done()
    assert calls() == 1

    freezer.tick(RAIN_FORECAST_TTL)
    await tracker.async_refresh(WEATHER)
    await hass.async_block_till_done()
    assert calls() == 2


async def test_past_days_are_remembered(
    hass: HomeAssistant, forecasts: Forecasts, freezer: FrozenDateTimeFactory
) -> None:
    """A day keeps its last forecast once it has passed; later ones overwrite."""
    forecasts["daily"] = [
        {"datetime": _local(_day(0), 12), "precipitation": 6.0},
        {"datetime": _local(_day(1), 12), "precipitation": 1.0},
    ]
    tracker = RainTracker(hass)
    await tracker.async_refresh(WEATHER)
    yesterday, today = _day(0), _day(1)

    freezer.tick(timedelta(days=1))
    forecasts["daily"] = [
        {"datetime": _local(today, 12), "precipitation": 3.0},
        {"datetime": _local(today + timedelta(days=1), 12), "precipitation": 0.0},
    ]
    await tracker.async_refresh(WEATHER)

    assert tracker.precipitation(WEATHER) == (
        _rain(yesterday, 6.0),
        _rain(today, 3.0),
        _rain(today + timedelta(days=1), 0.0),
    )


async def test_old_days_are_forgotten(
    hass: HomeAssistant, forecasts: Forecasts, freezer: FrozenDateTimeFactory
) -> None:
    """Days older than the history window are dropped."""
    forecasts["daily"] = [{"datetime": _local(_day(0)), "precipitation": 6.0}]
    tracker = RainTracker(hass)
    await tracker.async_refresh(WEATHER)

    freezer.tick(timedelta(days=RAIN_HISTORY_DAYS + 1))
    forecasts["daily"] = []
    await tracker.async_refresh(WEATHER)

    assert tracker.precipitation(WEATHER) == ()


@pytest.mark.parametrize(
    "failure", [HomeAssistantError("weather offline"), RuntimeError("boom")]
)
async def test_failed_fetch_keeps_known_rain(
    hass: HomeAssistant,
    forecasts: Forecasts,
    freezer: FrozenDateTimeFactory,
    failure: Exception,
) -> None:
    """A failing forecast keeps the cached days and raises nothing."""
    # Captured before the tick, which may cross local midnight.
    tomorrow = _day(1)
    forecasts["daily"] = [{"datetime": _local(tomorrow), "precipitation": 5.0}]
    tracker = RainTracker(hass)
    await tracker.async_refresh(WEATHER)

    freezer.tick(RAIN_FORECAST_TTL)
    forecasts["daily"] = failure
    forecasts["hourly"] = failure
    await tracker.async_refresh(WEATHER)

    assert tracker.precipitation(WEATHER) == (_rain(tomorrow, 5.0),)


async def test_missing_weather_action_is_tolerated(hass: HomeAssistant) -> None:
    """Without the weather integration there is simply no rain data."""
    tracker = RainTracker(hass)

    await tracker.async_refresh(WEATHER)

    assert tracker.precipitation(WEATHER) == ()


async def test_read_outdoor_uses_weather_attributes(hass: HomeAssistant) -> None:
    """Current temperature (to °C) and humidity come from the weather entity."""
    hass.states.async_set(
        WEATHER,
        "sunny",
        {"temperature": 77, "temperature_unit": "°F", "humidity": 40},
    )
    hass.states.async_set("sensor.bed", "30")

    reading = read_outdoor(hass, WEATHER, "sensor.bed")

    assert reading.temperature == pytest.approx(25.0)
    assert reading.humidity == 40.0
    assert reading.soil_moisture == 30.0


@pytest.mark.parametrize("entity_id", [WEATHER, "weather.gone", None])
async def test_read_outdoor_without_usable_weather(
    hass: HomeAssistant, entity_id: str | None
) -> None:
    """Unavailable, missing or unset weather gives no readings."""
    hass.states.async_set(WEATHER, STATE_UNAVAILABLE, {"temperature": 20})

    assert read_outdoor(hass, entity_id, None) == ClimateReading()


async def test_naive_forecast_times_are_local(
    hass: HomeAssistant, forecasts: Forecasts
) -> None:
    """A forecast time without an offset is read in HA's local zone."""
    naive = datetime.combine(_day(1), datetime.min.time()).isoformat()
    forecasts["daily"] = [{"datetime": naive, "precipitation": 1.0}]
    tracker = RainTracker(hass)

    await tracker.async_refresh(WEATHER)

    assert tracker.precipitation(WEATHER) == (_rain(_day(1), 1.0),)
