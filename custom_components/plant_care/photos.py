"""Plant photos uploaded in the plant flow, kept in `<config>/plant_care/photos`."""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
import re
import secrets
import shutil
from typing import Any, Final

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import CONF_PHOTO, CONF_PHOTO_UPLOAD, CONF_REMOVE_PHOTO, DOMAIN

MAX_PHOTO_BYTES: Final = 10 * 1024 * 1024

CONTENT_TYPES: Final = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Stored names are random, so a new upload never hits a cached old photo, and
# a name read from subentry data can never point outside the photo folder.
_NAME = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp)")


class InvalidPhoto(Exception):
    """The upload is missing, too large or not a JPEG, PNG or WebP image."""


def photo_path(hass: HomeAssistant, name: str) -> Path | None:
    """Where a stored photo lives; None for a name the integration never made."""
    if not _NAME.fullmatch(name):
        return None
    return _photo_dir(hass) / name


def content_type(name: str) -> str:
    """The MIME type of a stored photo, from its extension."""
    return CONTENT_TYPES[Path(name).suffix]


async def async_apply_photo(
    hass: HomeAssistant, form: Mapping[str, Any], current: str | None
) -> dict[str, Any]:
    """Subentry data from a submitted plant form, with the photo field resolved.

    A new upload is stored and replaces the photo; `remove_photo` drops it;
    otherwise the current photo is kept. The replaced file stays until the
    next setup prunes it.
    """
    data = {
        key: value
        for key, value in form.items()
        if key not in (CONF_PHOTO_UPLOAD, CONF_REMOVE_PHOTO)
    }
    if file_id := form.get(CONF_PHOTO_UPLOAD):
        data[CONF_PHOTO] = await hass.async_add_executor_job(
            _store_upload, hass, file_id
        )
    elif current and not form.get(CONF_REMOVE_PHOTO):
        data[CONF_PHOTO] = current
    return data


async def async_prune_photos(hass: HomeAssistant, keep: set[str]) -> None:
    """Delete stored photos no plant refers to."""
    await hass.async_add_executor_job(_prune, _photo_dir(hass), keep)


def photo_updated_at(path: Path) -> datetime | None:
    """When the photo file was written; None if it is gone. Blocking."""
    try:
        return dt_util.utc_from_timestamp(path.stat().st_mtime)
    except OSError:
        return None


def _photo_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(DOMAIN, "photos"))


def _store_upload(hass: HomeAssistant, file_id: str) -> str:
    """Copy a checked upload into the photo folder; returns its stored name."""
    try:
        with process_uploaded_file(hass, file_id) as upload:
            if upload.stat().st_size > MAX_PHOTO_BYTES:
                raise InvalidPhoto
            with upload.open("rb") as file:
                extension = _image_extension(file.read(12))
            if extension is None:
                raise InvalidPhoto
            directory = _photo_dir(hass)
            directory.mkdir(parents=True, exist_ok=True)
            name = f"{secrets.token_hex(16)}{extension}"
            shutil.copyfile(upload, directory / name)
    except ValueError as err:  # unknown or expired upload
        raise InvalidPhoto from err
    return name


def _image_extension(head: bytes) -> str | None:
    """The extension for an image's leading bytes (its magic number)."""
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


def _prune(directory: Path, keep: set[str]) -> None:
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_file() and path.name not in keep:
            path.unlink()
