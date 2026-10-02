# Home Assistant integration conventions

Applies to all code under `custom_components/plant_care/` except `core/`.

## Conventions
- Async only: HTTP through `aiohttp` from `async_get_clientsession`, files through `Store`; nothing blocks the event loop.
- Typed config entry: `type PlantCareConfigEntry = ConfigEntry[PlantCareRuntimeData]`; runtime state in `entry.runtime_data`, never `hass.data`.
- Every user-facing text (flows, errors, entities, actions) lives in `strings.json` and `translations/*.json`. `translations/en.json` is a copy of `strings.json`; `ru.json` is the only non-English file in the repo.
- Translation strings carry no URLs (hassfest rejects them): pass links as `description_placeholders`.
- Time in UTC (`dt_util.utcnow()`); local time only for display.
- Logging via `_LOGGER = logging.getLogger(__name__)`, with secrets (client secret, tokens) kept out of every message.

## Flows
- Form errors are translation keys in `errors`; entered values are kept on error via `add_suggested_values_to_schema`.
- Reconfigure saves with `async_update_reload_and_abort(..., data=...)` (full replace) when cleared optional fields must disappear; `data_updates` merges and cannot remove keys.

## Verified APIs (for the pinned HA 2026.9)
- Subentries: `ConfigFlow.async_get_supported_subentry_types()` → `{"plant": PlantSubentryFlow}`; in a subentry `reconfigure` use `self._get_entry()` and `self._get_reconfigure_subentry()`. A subentry flow never learns the `subentry_id` it creates.
- Since HA 2026.8 a device has exactly one config entry (hence minimum 2026.8.0 in `hacs.json`): read `device.config_entry_id` / `device.config_subentry_id` (`device.config_entries_subentries` is deprecated); move a device with `async_update_device(new_config_entry_id=..., new_config_subentry_id=...)`.
- Schemas use `voluptuous` (`import voluptuous as vol`). The developer docs already show `probatio`, but HA 2026.9 types its flow API with `vol.Schema` and no core flow uses `probatio`; switch only after bumping the HA pin to a version that accepts it.
- Single instance: `"single_config_entry": true` in `manifest.json`, no check in the flow.

## Checking an API
Current docs first (context7 `/home-assistant/developers.home-assistant`), then the installed source in the dev container (`/home/vscode/.venv/lib/python3.14/site-packages/homeassistant/`). The docs can run ahead of the pinned version; the installed source is what the code runs against.
