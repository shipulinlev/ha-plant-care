# Testing

## Layout
- `tests/core/`: engine unit tests, no HA, fast, run on Windows too. `tests/core/conftest.py` overrides the HA autouse fixture with a no-op: any new HA-dependent autouse fixture in `tests/conftest.py` needs a no-op override there as well.
- `tests/test_*.py`: integration tests on `pytest-homeassistant-custom-component` (dev container only): the `hass` fixture, `MockConfigEntry` (with `subentries_data` for plants), `aioclient_mock` for OpenPlantbook, never real network. `tests/conftest.py` provides `plant_entry`: a loaded hub with one indoor plant, Ficus (water every 7 days, feed every 30).

## Translations
`tests/test_translations.py` fails when `translations/en.json` drifts from `strings.json`, when `ru.json` misses or adds a key or changes a placeholder, or when a flow step shows a field without a label. After editing `strings.json`, copy it to `translations/en.json` and add the Russian text.

## Coverage the integration must keep
Hub flow and plant flow including every error, area change → climate sources re-resolved, every action, entry unload with no leaked listeners.

## Gotchas
- A fixture that builds a client on `async_get_clientsession(hass)` must depend on `aioclient_mock`, or the session is created before the mock and tries the real network. Such fixtures must be `async`.
- `aioclient_mock` serves the first registered match; for changing responses (401 then 200) use `side_effect`.
- Patch OpenPlantbook calls in flow tests at `custom_components.plant_care.flow_helpers.OpenPlantbookClient.<method>`.
- `MockConfigEntry.start_reconfigure_flow` / `start_subentry_reconfigure_flow` start reconfigure flows.
- A test that passes on its first run proves nothing: break the code on purpose and watch it fail before trusting it.
