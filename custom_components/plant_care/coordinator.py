"""Coordinator: the care plan of every plant, recomputed on change."""

from dataclasses import replace
from datetime import datetime, timedelta
import logging
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .climate import async_indoor_sources, read_indoor, read_outdoor
from .const import (
    CONF_LOCATION_TYPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SPECIES_PID,
    CONF_WEATHER_ENTITY,
    DOMAIN,
)
from .core.engine import CareEngine
from .core.models import (
    CareEvent,
    CarePlan,
    ClimateReading,
    LocationType,
    SpeciesProfile,
)
from .openplantbook import OpenPlantbookClient, OpenPlantbookError
from .plants import plant_config, plant_subentries, with_overrides
from .rain import RainTracker
from .storage import CareLog, ProfileCache

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL: Final = timedelta(minutes=30)
# After a failed OpenPlantbook call, serve the cache this long before retrying.
PROFILE_RETRY_AFTER: Final = timedelta(hours=1)
# Entity registry changes that can move a sensor into or out of a plant's sources.
_SOURCE_FIELDS: Final = frozenset(
    {"area_id", "device_id", "device_class", "original_device_class", "disabled_by"}
)


class PlantCareCoordinator(DataUpdateCoordinator[dict[str, CarePlan]]):
    """Care plans keyed by plant (subentry) id."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        care_log: CareLog,
        profile_cache: ProfileCache,
        client: OpenPlantbookClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.care_log = care_log
        self.profile_cache = profile_cache
        self._client = client
        self._rain = RainTracker(hass)
        self._engine = CareEngine()
        self._profile_failed_at: dict[str, datetime] = {}
        self._tracked: frozenset[str] = frozenset()
        self._unsub_states: CALLBACK_TYPE | None = None

    async def async_log_care(self, event: CareEvent) -> None:
        """Record a watering or feeding and recompute at once."""
        await self.care_log.async_add(event)
        await self.async_refresh()

    @callback
    def async_listen_registries(self) -> None:
        """Recompute when a plant or a sensor moves; stops on entry unload."""
        for event_type, event_filter in (
            (dr.EVENT_DEVICE_REGISTRY_UPDATED, _device_moved),
            (er.EVENT_ENTITY_REGISTRY_UPDATED, _entity_source_changed),
        ):
            self.config_entry.async_on_unload(
                self.hass.bus.async_listen(
                    event_type, self._async_on_registry_change, event_filter
                )
            )

    async def async_shutdown(self) -> None:
        """Stop the state subscriptions along with the timer."""
        self._untrack()
        await super().async_shutdown()

    async def _async_update_data(self) -> dict[str, CarePlan]:
        now = dt_util.utcnow()
        sources: set[str] = set()
        plans: dict[str, CarePlan] = {}
        for subentry in plant_subentries(self.config_entry):
            climate = await self._async_climate(subentry, sources)
            profile = await self._async_profile(subentry.data.get(CONF_SPECIES_PID))
            plans[subentry.subentry_id] = self._engine.plan(
                plant=plant_config(subentry),
                events=self.care_log.events(subentry.subentry_id),
                climate=climate,
                profile=with_overrides(profile, subentry.data),
                now=now,
                latitude=self.hass.config.latitude,
            )
        self._track(sources)
        return plans

    async def _async_climate(
        self, subentry: ConfigSubentry, sources: set[str]
    ) -> ClimateReading:
        """Read a plant's climate and add the entities it used to `sources`."""
        data = subentry.data
        soil = data.get(CONF_SOIL_MOISTURE_ENTITY)
        if soil:
            sources.add(soil)
        if data[CONF_LOCATION_TYPE] == LocationType.INDOOR:
            indoor = async_indoor_sources(self.hass, self._area_of(subentry))
            sources.update(indoor.entity_ids)
            return read_indoor(self.hass, indoor, soil)
        weather = data.get(CONF_WEATHER_ENTITY) or self.config_entry.data.get(
            CONF_WEATHER_ENTITY
        )
        climate = read_outdoor(self.hass, weather, soil)
        if not weather:
            return climate
        sources.add(weather)
        await self._rain.async_refresh(weather)
        return replace(climate, precipitation=self._rain.precipitation(weather))

    async def _async_profile(self, pid: str | None) -> SpeciesProfile | None:
        """Cached species profile, refetched when stale; cache on failure."""
        if not pid:
            return None
        failed_at = self._profile_failed_at.get(pid)
        retry = failed_at is None or dt_util.utcnow() - failed_at >= PROFILE_RETRY_AFTER
        if self.profile_cache.needs_refresh(pid) and retry:
            try:
                profile = await self._client.async_get_profile(pid)
            except OpenPlantbookError as err:
                self._profile_failed_at[pid] = dt_util.utcnow()
                _LOGGER.warning(
                    "Could not fetch species %s from OpenPlantbook, using cached "
                    "data if any: %s",
                    pid,
                    err,
                )
            else:
                self._profile_failed_at.pop(pid, None)
                await self.profile_cache.async_set(pid, profile)
        return self.profile_cache.get(pid)

    def _area_of(self, subentry: ConfigSubentry) -> str | None:
        device = dr.async_get(self.hass).async_get_device_by_identifier(
            (DOMAIN, subentry.subentry_id), self.config_entry.entry_id
        )
        return device.area_id if device else None

    def _track(self, entity_ids: set[str]) -> None:
        """Follow the state of exactly these source entities."""
        if entity_ids == self._tracked:
            return
        self._untrack()
        self._tracked = frozenset(entity_ids)
        if entity_ids:
            self._unsub_states = async_track_state_change_event(
                self.hass, sorted(entity_ids), self._async_on_source_state
            )

    def _untrack(self) -> None:
        if self._unsub_states is not None:
            self._unsub_states()
            self._unsub_states = None
        self._tracked = frozenset()

    @callback
    def _async_on_source_state(self, event: Event[Any]) -> None:
        # Debounced: sensors may report often.
        self.config_entry.async_create_task(self.hass, self.async_request_refresh())

    @callback
    def _async_on_registry_change(self, event: Event[Any]) -> None:
        # Rare and user-driven: recompute at once.
        self.config_entry.async_create_task(self.hass, self.async_refresh())


@callback
def _device_moved(event_data: Any) -> bool:
    return event_data["action"] == "update" and "area_id" in event_data["changes"]


@callback
def _entity_source_changed(event_data: Any) -> bool:
    if event_data["action"] != "update":
        return True
    return not _SOURCE_FIELDS.isdisjoint(event_data["changes"])
