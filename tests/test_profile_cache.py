"""Tests for the OpenPlantbook species profile cache."""

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant

from custom_components.plant_care.core.models import SpeciesProfile
from custom_components.plant_care.storage import (
    PROFILE_CACHE_STORAGE_KEY,
    PROFILE_CACHE_STORAGE_VERSION,
    PROFILE_CACHE_TTL,
    ProfileCache,
)

PID = "monstera deliciosa"
PROFILE = SpeciesProfile(
    min_temp=12,
    max_temp=32,
    min_env_humid=30,
    max_env_humid=85,
    min_soil_moist=15,
    max_soil_moist=60,
)


async def _loaded(hass: HomeAssistant) -> ProfileCache:
    cache = ProfileCache(hass)
    await cache.async_load()
    return cache


async def test_unknown_species_is_missing_and_needs_refresh(
    hass: HomeAssistant,
) -> None:
    """A species never fetched has no profile and must be fetched."""
    cache = await _loaded(hass)

    assert cache.get(PID) is None
    assert cache.needs_refresh(PID)


async def test_stored_profile_is_fresh(hass: HomeAssistant) -> None:
    """A just-stored profile is returned and needs no refresh."""
    cache = await _loaded(hass)

    await cache.async_set(PID, PROFILE)

    assert cache.get(PID) == PROFILE
    assert not cache.needs_refresh(PID)


async def test_profile_past_ttl_needs_refresh_but_is_still_served(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """An expired profile is refetched, but stays usable while offline."""
    cache = await _loaded(hass)
    await cache.async_set(PID, PROFILE)

    freezer.tick(PROFILE_CACHE_TTL - timedelta(minutes=1))
    assert not cache.needs_refresh(PID)

    freezer.tick(timedelta(minutes=2))
    assert cache.needs_refresh(PID)
    assert cache.get(PID) == PROFILE


async def test_profiles_survive_reload(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Profiles and their fetch time are persisted."""
    cache = await _loaded(hass)
    partial = SpeciesProfile(min_temp=5)
    await cache.async_set(PID, partial)

    assert (
        hass_storage[PROFILE_CACHE_STORAGE_KEY]["version"]
        == PROFILE_CACHE_STORAGE_VERSION
    )
    freezer.tick(PROFILE_CACHE_TTL + timedelta(days=1))
    reloaded = await _loaded(hass)
    assert reloaded.get(PID) == partial
    assert reloaded.needs_refresh(PID)


async def test_remove_drops_profile_persistently(hass: HomeAssistant) -> None:
    """Removing a profile forces a refetch, also after reload."""
    cache = await _loaded(hass)
    await cache.async_set(PID, PROFILE)

    await cache.async_remove(PID)

    reloaded = await _loaded(hass)
    assert reloaded.get(PID) is None
    assert reloaded.needs_refresh(PID)


async def test_remove_unknown_profile_is_a_no_op(hass: HomeAssistant) -> None:
    """Removing a species that is not cached does not fail."""
    cache = await _loaded(hass)

    await cache.async_remove("missing")

    assert cache.get("missing") is None
