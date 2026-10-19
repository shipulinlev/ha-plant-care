"""Tests for the plant photo entity and the photo folder."""

from http import HTTPStatus
from pathlib import Path

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import (
    ATTR_ENTITY_PICTURE,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_NAME,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.plant_care.const import (
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_PHOTO,
    CONF_WATERING_INTERVAL,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)

from .conftest import FICUS_IMAGE, JPEG

PHOTO = "a" * 32 + ".jpg"


def _store(path: Path, content: bytes = JPEG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _names(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


async def _hub_with_photo(hass: HomeAssistant, photo: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_CLIENT_ID: "id", CONF_CLIENT_SECRET: "secret"},
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_NAME: "Ficus",
                    CONF_LOCATION_TYPE: "indoor",
                    CONF_WATERING_INTERVAL: 7,
                    CONF_FEEDING_INTERVAL: 30,
                    CONF_PHOTO: photo,
                },
                subentry_type=SUBENTRY_TYPE_PLANT,
                title="Ficus",
                unique_id=None,
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_photo_belongs_to_the_plant(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """The photo entity is bound to the plant's device and subentry."""
    (subentry_id,) = plant_entry.subentries
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, subentry_id), plant_entry.entry_id
    )
    entity = er.async_get(hass).async_get("image.ficus_photo")
    assert entity is not None
    assert device is not None
    assert entity.unique_id == f"{subentry_id}_photo"
    assert entity.device_id == device.id
    assert entity.config_subentry_id == subentry_id
    assert entity.translation_key == "photo"


async def test_no_photo_without_upload_or_species(
    hass: HomeAssistant, plant_entry: MockConfigEntry
) -> None:
    """A plant without a photo or species has an image entity with no picture."""
    state = hass.states.get("image.ficus_photo")
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert ATTR_ENTITY_PICTURE not in state.attributes


async def test_species_photo_without_upload(
    hass: HomeAssistant, species_entry: MockConfigEntry
) -> None:
    """Without an upload the picture is the OpenPlantbook species photo."""
    state = hass.states.get("image.ficus_photo")
    assert state is not None
    assert state.attributes[ATTR_ENTITY_PICTURE] == FICUS_IMAGE


async def test_uploaded_photo_is_served(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    photo_dir: Path,
) -> None:
    """An uploaded photo goes through HA's image proxy, dated by its file."""
    await hass.async_add_executor_job(_store, photo_dir / PHOTO)
    await _hub_with_photo(hass, PHOTO)

    state = hass.states.get("image.ficus_photo")
    assert state is not None
    assert state.state != STATE_UNKNOWN
    picture = state.attributes[ATTR_ENTITY_PICTURE]
    assert picture.startswith("/api/image_proxy/image.ficus_photo?token=")

    client = await hass_client()
    response = await client.get(picture)
    assert response.status == HTTPStatus.OK
    assert response.content_type == "image/jpeg"
    assert await response.read() == JPEG


async def test_setup_prunes_photos_no_plant_uses(
    hass: HomeAssistant, photo_dir: Path
) -> None:
    """Photos of deleted plants and replaced photos are removed at setup."""
    await hass.async_add_executor_job(_store, photo_dir / PHOTO)
    await hass.async_add_executor_job(_store, photo_dir / ("b" * 32 + ".png"))

    await _hub_with_photo(hass, PHOTO)

    assert await hass.async_add_executor_job(_names, photo_dir) == [PHOTO]


async def test_unknown_photo_name_is_ignored(
    hass: HomeAssistant, photo_dir: Path
) -> None:
    """A name the integration never made cannot point outside the photo folder."""
    await hass.async_add_executor_job(_store, photo_dir.parent / "secret.jpg")

    await _hub_with_photo(hass, "../secret.jpg")

    state = hass.states.get("image.ficus_photo")
    assert state is not None
    assert ATTR_ENTITY_PICTURE not in state.attributes
