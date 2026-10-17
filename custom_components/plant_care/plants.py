"""Plant subentries as engine inputs."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry

from .const import (
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_WATERING_INTERVAL,
    RANGE_OVERRIDES,
    SUBENTRY_TYPE_PLANT,
)
from .core.models import LocationType, PlantConfig, SpeciesProfile


def plant_subentries(entry: ConfigEntry) -> list[ConfigSubentry]:
    """The hub's plants."""
    return [
        subentry
        for subentry in entry.subentries.values()
        if subentry.subentry_type == SUBENTRY_TYPE_PLANT
    ]


def plant_config(subentry: ConfigSubentry) -> PlantConfig:
    """The engine's view of a plant's settings."""
    return PlantConfig(
        plant_id=subentry.subentry_id,
        location_type=LocationType(subentry.data[CONF_LOCATION_TYPE]),
        initial_watering_interval_days=float(subentry.data[CONF_WATERING_INTERVAL]),
        feeding_interval_days=float(subentry.data[CONF_FEEDING_INTERVAL]),
    )


def with_overrides(
    profile: SpeciesProfile | None, data: Mapping[str, Any]
) -> SpeciesProfile | None:
    """The species profile with the plant's range overrides on top."""
    # Typed loosely: the keys are range fields only, never `display_pid`.
    overrides: dict[str, Any] = {
        key: float(data[key])
        for pair in RANGE_OVERRIDES
        for key in pair
        if data.get(key) is not None
    }
    if not overrides:
        return profile
    return replace(profile or SpeciesProfile(), **overrides)
