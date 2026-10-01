"""Tests for the care history store."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.plant_care.core.models import CareEvent, CareKind
from custom_components.plant_care.storage import (
    CARE_LOG_STORAGE_KEY,
    CARE_LOG_STORAGE_VERSION,
    CareLog,
)

T0 = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def _event(plant_id: str, kind: CareKind, at: datetime) -> CareEvent:
    return CareEvent(plant_id=plant_id, kind=kind, at=at)


async def _loaded(hass: HomeAssistant) -> CareLog:
    log = CareLog(hass)
    await log.async_load()
    return log


async def test_empty_store_has_no_events(hass: HomeAssistant) -> None:
    """A fresh installation has no history for any plant."""
    log = await _loaded(hass)

    assert log.events("plant_a") == ()


async def test_added_events_are_returned_in_time_order(hass: HomeAssistant) -> None:
    """Events come back sorted by time, even when backdated out of order."""
    log = await _loaded(hass)
    later = _event("plant_a", CareKind.WATERED, T0 + timedelta(days=3))
    earlier = _event("plant_a", CareKind.FED, T0)

    await log.async_add(later)
    await log.async_add(earlier)

    assert log.events("plant_a") == (earlier, later)


async def test_events_are_kept_per_plant(hass: HomeAssistant) -> None:
    """One plant's history does not leak into another's."""
    log = await _loaded(hass)
    event_a = _event("plant_a", CareKind.WATERED, T0)
    event_b = _event("plant_b", CareKind.WATERED, T0)

    await log.async_add(event_a)
    await log.async_add(event_b)

    assert log.events("plant_a") == (event_a,)
    assert log.events("plant_b") == (event_b,)


async def test_added_events_survive_reload(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """History is persisted and read back by a new CareLog."""
    log = await _loaded(hass)
    event = _event("plant_a", CareKind.WATERED, T0)
    await log.async_add(event)

    assert hass_storage[CARE_LOG_STORAGE_KEY]["version"] == CARE_LOG_STORAGE_VERSION
    reloaded = await _loaded(hass)
    assert reloaded.events("plant_a") == (event,)


async def test_non_utc_times_are_stored_as_utc(hass: HomeAssistant) -> None:
    """A backdated time in a local zone is normalized to UTC."""
    log = await _loaded(hass)
    local = datetime(2026, 9, 1, 11, 0, tzinfo=timezone(timedelta(hours=3)))
    await log.async_add(_event("plant_a", CareKind.WATERED, local))

    reloaded = await _loaded(hass)
    (event,) = reloaded.events("plant_a")
    assert event.at == T0
    assert event.at.tzinfo == UTC


async def test_loads_existing_storage(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """History written by a previous run is loaded on startup."""
    hass_storage[CARE_LOG_STORAGE_KEY] = {
        "version": CARE_LOG_STORAGE_VERSION,
        "minor_version": 1,
        "key": CARE_LOG_STORAGE_KEY,
        "data": {
            "plants": {
                "plant_a": [{"kind": "fed", "at": "2026-09-01T08:00:00+00:00"}],
            }
        },
    }

    log = await _loaded(hass)

    assert log.events("plant_a") == (_event("plant_a", CareKind.FED, T0),)


async def test_remove_plant_deletes_only_its_history(hass: HomeAssistant) -> None:
    """Deleting a plant drops its history, persistently, and keeps the others."""
    log = await _loaded(hass)
    event_b = _event("plant_b", CareKind.WATERED, T0)
    await log.async_add(_event("plant_a", CareKind.WATERED, T0))
    await log.async_add(event_b)

    await log.async_remove_plant("plant_a")

    reloaded = await _loaded(hass)
    assert reloaded.events("plant_a") == ()
    assert reloaded.events("plant_b") == (event_b,)


async def test_remove_unknown_plant_is_a_no_op(hass: HomeAssistant) -> None:
    """Removing a plant without history does not fail."""
    log = await _loaded(hass)

    await log.async_remove_plant("missing")

    assert log.events("missing") == ()
