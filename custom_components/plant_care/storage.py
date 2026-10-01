"""Persistent data: care history of all plants and cached species profiles."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Final, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .core.models import CareEvent, CareKind, SpeciesProfile

CARE_LOG_STORAGE_KEY: Final = f"{DOMAIN}.care_log"
CARE_LOG_STORAGE_VERSION: Final = 1

PROFILE_CACHE_STORAGE_KEY: Final = f"{DOMAIN}.species_profiles"
PROFILE_CACHE_STORAGE_VERSION: Final = 1
# Species ranges hardly ever change; this only bounds how stale they get.
PROFILE_CACHE_TTL: Final = timedelta(days=30)


class _StoredEvent(TypedDict):
    kind: str
    at: str


class _CareLogData(TypedDict):
    plants: dict[str, list[_StoredEvent]]


class CareLog:
    """Watering and feeding events, keyed by plant (subentry) id."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[_CareLogData] = Store(
            hass, CARE_LOG_STORAGE_VERSION, CARE_LOG_STORAGE_KEY
        )
        self._events: dict[str, list[CareEvent]] = {}

    async def async_load(self) -> None:
        """Read the history from disk."""
        data = await self._store.async_load()
        if data is None:
            return
        self._events = {
            plant_id: sorted(
                (
                    CareEvent(
                        plant_id=plant_id,
                        kind=CareKind(row["kind"]),
                        at=datetime.fromisoformat(row["at"]),
                    )
                    for row in rows
                ),
                key=lambda event: event.at,
            )
            for plant_id, rows in data["plants"].items()
        }

    def events(self, plant_id: str) -> tuple[CareEvent, ...]:
        """All events of a plant, oldest first."""
        return tuple(self._events.get(plant_id, ()))

    async def async_add(self, event: CareEvent) -> None:
        """Record an event (times are stored in UTC) and persist."""
        event = CareEvent(
            plant_id=event.plant_id, kind=event.kind, at=event.at.astimezone(UTC)
        )
        events = self._events.setdefault(event.plant_id, [])
        events.append(event)
        events.sort(key=lambda item: item.at)
        await self._async_save()

    async def async_remove_plant(self, plant_id: str) -> None:
        """Delete the whole history of a plant and persist."""
        if self._events.pop(plant_id, None) is not None:
            await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "plants": {
                    plant_id: [
                        {"kind": event.kind.value, "at": event.at.isoformat()}
                        for event in events
                    ]
                    for plant_id, events in self._events.items()
                }
            }
        )


class _StoredProfile(TypedDict):
    fetched_at: str
    profile: dict[str, float | None]


class _ProfileCacheData(TypedDict):
    profiles: dict[str, _StoredProfile]


class ProfileCache:
    """OpenPlantbook profiles keyed by species PID, served even when expired."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[_ProfileCacheData] = Store(
            hass, PROFILE_CACHE_STORAGE_VERSION, PROFILE_CACHE_STORAGE_KEY
        )
        self._profiles: dict[str, tuple[datetime, SpeciesProfile]] = {}

    async def async_load(self) -> None:
        """Read the cached profiles from disk."""
        data = await self._store.async_load()
        if data is None:
            return
        self._profiles = {
            pid: (
                datetime.fromisoformat(row["fetched_at"]),
                SpeciesProfile(**row["profile"]),
            )
            for pid, row in data["profiles"].items()
        }

    def get(self, pid: str) -> SpeciesProfile | None:
        """The cached profile of a species, whatever its age."""
        cached = self._profiles.get(pid)
        return cached[1] if cached else None

    def needs_refresh(self, pid: str) -> bool:
        """Whether the profile is missing or older than the TTL."""
        cached = self._profiles.get(pid)
        return cached is None or dt_util.utcnow() - cached[0] >= PROFILE_CACHE_TTL

    async def async_set(self, pid: str, profile: SpeciesProfile) -> None:
        """Store a freshly fetched profile and persist."""
        self._profiles[pid] = (dt_util.utcnow(), profile)
        await self._async_save()

    async def async_remove(self, pid: str) -> None:
        """Drop a profile so it is fetched again, and persist."""
        if self._profiles.pop(pid, None) is not None:
            await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "profiles": {
                    pid: {
                        "fetched_at": fetched_at.isoformat(),
                        "profile": asdict(profile),
                    }
                    for pid, (fetched_at, profile) in self._profiles.items()
                }
            }
        )
