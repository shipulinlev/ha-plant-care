"""Persistent care history of all plants."""

from datetime import UTC, datetime
from typing import Final, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .core.models import CareEvent, CareKind

CARE_LOG_STORAGE_KEY: Final = f"{DOMAIN}.care_log"
CARE_LOG_STORAGE_VERSION: Final = 1


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
