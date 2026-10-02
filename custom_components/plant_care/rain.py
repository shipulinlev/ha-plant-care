"""Daily rain per weather entity, from forecasts, remembered after the day passes.

Weather entities only forecast, so the last forecast of a day stands in for
the rain that fell; it is the "past precipitation" the engine needs.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta
import logging
from typing import Any, Final

from homeassistant.components.weather.const import ATTR_WEATHER_PRECIPITATION_UNIT
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter

from .core.models import Precipitation

_LOGGER = logging.getLogger(__name__)

# Forecasts change slowly; one call per weather entity and TTL.
RAIN_FORECAST_TTL: Final = timedelta(hours=1)
# Past days kept, longer than any realistic watering interval.
RAIN_HISTORY_DAYS: Final = 14
# Daily totals are the engine's unit; hourly is the fallback.
_FORECAST_TYPES: Final = ("daily", "hourly")


class RainTracker:
    """Daily precipitation (mm) per weather entity; in memory only."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._days: dict[str, dict[date, float]] = {}
        self._fetched: dict[str, datetime] = {}

    async def async_refresh(self, entity_id: str) -> None:
        """Fetch the forecast unless the last fetch is younger than the TTL."""
        now = dt_util.utcnow()
        fetched = self._fetched.get(entity_id)
        if fetched is not None and now - fetched < RAIN_FORECAST_TTL:
            return
        self._fetched[entity_id] = now

        days = self._days.setdefault(entity_id, {})
        today = dt_util.now().date()
        forecast = await self._async_forecast(entity_id)
        if forecast is not None:
            # Today and later always come from the newest forecast.
            for day in [day for day in days if day >= today]:
                del days[day]
            days.update(_daily_totals(forecast, self._precipitation_unit(entity_id)))
        cutoff = today - timedelta(days=RAIN_HISTORY_DAYS)
        for day in [day for day in days if day < cutoff]:
            del days[day]

    def precipitation(self, entity_id: str) -> tuple[Precipitation, ...]:
        """Known daily rain, oldest first, each at the start of its local day."""
        return tuple(
            Precipitation(
                at=dt_util.as_utc(dt_util.start_of_local_day(day)), amount_mm=amount
            )
            for day, amount in sorted(self._days.get(entity_id, {}).items())
        )

    async def _async_forecast(self, entity_id: str) -> list[dict[str, Any]] | None:
        for forecast_type in _FORECAST_TYPES:
            try:
                response = await self._hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"type": forecast_type},
                    target={"entity_id": entity_id},
                    blocking=True,
                    return_response=True,
                )
            except HomeAssistantError as err:
                _LOGGER.debug(
                    "No %s forecast from %s: %s", forecast_type, entity_id, err
                )
                continue
            except Exception:
                _LOGGER.exception(
                    "Unexpected error getting the %s forecast of %s",
                    forecast_type,
                    entity_id,
                )
                continue
            result = (response or {}).get(entity_id)
            forecast = result.get("forecast") if isinstance(result, dict) else None
            if isinstance(forecast, list):
                return [entry for entry in forecast if isinstance(entry, dict)]
        return None

    def _precipitation_unit(self, entity_id: str) -> str:
        state = self._hass.states.get(entity_id)
        unit = state.attributes.get(ATTR_WEATHER_PRECIPITATION_UNIT) if state else None
        return str(unit) if unit else UnitOfLength.MILLIMETERS


def _daily_totals(forecast: list[dict[str, Any]], unit: str) -> dict[date, float]:
    """Sum precipitation per local day, in mm; entries without a value are skipped."""
    totals: dict[date, float] = defaultdict(float)
    for entry in forecast:
        amount = entry.get("precipitation")
        at = dt_util.parse_datetime(str(entry.get("datetime", "")))
        if not isinstance(amount, int | float) or at is None:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=dt_util.get_default_time_zone())
        totals[dt_util.as_local(at).date()] += DistanceConverter.convert(
            float(amount), unit, UnitOfLength.MILLIMETERS
        )
    return dict(totals)
