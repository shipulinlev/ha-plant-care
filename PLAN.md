# PLAN.md — roadmap and progress

Statuses: `[ ]` not started · `[~]` in progress · `[x]` done (tests, ruff and mypy green) · `[-]` dropped.
Update rules are in `CLAUDE.md` ("Workflow"). Items tracked as GitHub issues carry the reference: `(#N)`.

**Current phase:** 6. Live HA check and release
**Next step:** phase 6, manual run on a test HA (then calibration, license, brand assets, release)

---

## Phase 0. Project scaffolding
- [x] Architecture concepts, `CLAUDE.md`, `README.md`, `PLAN.md`
- [x] `git init` (branch `main`), `.gitignore`, `.gitattributes` (LF)
- [x] `pyproject.toml`: dev dependencies via `[dependency-groups]`, pytest, ruff and mypy (strict) settings
  - Dev environment: Python 3.14.3, HA 2026.9.4 (via `pytest-homeassistant-custom-component==0.13.367`), ruff 0.16.9, mypy 2.3.1, pytest 9.0.3.
  - The `homeassistant` import ban in `core/` and `tests/core/` is ruff rule `TID251`, verified on probe files.
- [x] Dev container for integration tests and a live HA (the HA pytest plugin fails on Windows because of `fcntl`)
  - `.devcontainer/` (image `mcr.microsoft.com/devcontainers/python:3.14` + ffmpeg, libturbojpeg, libpcap), scripts `scripts/setup`, `scripts/test`, `scripts/develop`.
  - Verified: a smoke test with the `hass` fixture passes, `scripts/develop` starts HA 2026.9.4 without errors, the frontend returns 200.
  - Dev HA config has no `default_config`: `go2rtc` needs a binary.
- [x] Agent skills setup (mattpocock-skills): GitHub Issues tracker, default triage labels, single-context domain docs (`docs/agents/`)
- [x] Install and authenticate the `gh` CLI (needed by the issue-tracker skills)
  - Triage labels created on GitHub (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`; `wontfix` is a GitHub default).
- [x] Skeleton of `custom_components/plant_care/`: `manifest.json`, `const.py`, `__init__.py`, `hacs.json`
  - `__init__.py` has `CONFIG_SCHEMA = config_entry_only_config_schema` (UI-only) and a no-op `async_setup` (actions will be registered there).
  - `manifest.json`: `config_flow: false` until phase 3; `integration_type: hub`, `iot_class: cloud_polling` (OpenPlantbook).
  - Tests: `tests/test_init.py` (manifest discovery, setup); `pythonpath = ["."]` in pytest config; `tests/core/conftest.py` overrides the HA autouse fixture so core tests run on Windows.
- [x] Pin the minimum HA version: `2026.8.0` in `hacs.json` (`manifest.json` has no min-version field for custom integrations)
  - Correction: the single-config-entry-per-device change landed in HA **2026.8**, not 2026.07 (developers blog 2026-07-21).
- [x] CI (GitHub Actions): pytest, ruff, mypy, hassfest, HACS validation
  - First run: lint/tests and hassfest green; HACS failed on missing license and topics. Fixed: MIT `LICENSE`, repo topics set via `gh`; all three jobs green since `aaadee8`.

## Phase 1. Core: models and engine (no HA, TDD)
- [x] `core/models.py`: `PlantConfig`, `SpeciesProfile`, `CareEvent`, `ClimateReading`, `CarePlan`, status enums
  - Frozen keyword-only dataclasses; `CareEvent` / `Precipitation` reject naive datetimes. `ClimateStatus`: `ok` | `out_of_range` | `unknown`. `CarePlan` also carries `last_watered` / `last_fed`.
- [x] Base watering interval: median of the last N intervals, fallback to `initial_watering_interval_days`
  - `core/history.py`: future events ignored; events within 6 h of the previous one are merged (double button press).
- [x] Climate multiplier from temperature and humidity relative to the species range, clamped to 0.5–1.5
  - `core/climate_factor.py`: deviation = distance outside the range / range width; temp factor `1 - dev`, humidity factor `1 + dev` (signed), multiplied, then clamped. A variable counts only with a reading and both bounds.
- [x] Precipitation handling for outdoor plants
  - Each entry ≥ 5 mm counts as watering if it falls after the last watering and no later than the scheduled date; it restarts the interval. Forecast rain is trusted as is.
- [x] Soil moisture sensor priority
  - Dry → next = now (keeps `overdue` if already overdue); wet → status `ok`, next no earlier than now + 1 d. Ignored without the species soil range.
- [x] Feeding: interval + seasonal factor (hemisphere from latitude)
  - `core/season.py`: spring/summer x1.0, autumn x1.5, winter x2.0. No winter pause for now.
- [x] `ok/soon/due/overdue` statuses and `explanation`
  - `core/status.py`: `soon` within 1 d before, `due` from the date, `overdue` from 1 d after. All windows live in `EngineSettings`.
- [x] Edge cases: no history, no climate, no species profile, future events, duplicate events

## Phase 2. Storage and external data
- [x] `storage.py`: `CareLog` on `Store` (version, migrations, deleting a plant's history)
  - Key `plant_care.care_log`, version 1, `{"plants": {plant_id: [{kind, at}]}}`; times normalized to UTC; events sorted oldest first. Saved immediately (care events are rare). No migration code until the schema reaches version 2 (YAGNI).
- [x] `storage.py`: OpenPlantbook profile cache with TTL
  - `ProfileCache`: key `plant_care.species_profiles`, version 1, TTL 30 days. `get` serves a profile of any age (offline use); `needs_refresh` tells the caller when to refetch; `async_remove` backs `refresh_species`. Only the fields of `SpeciesProfile` are cached (no light/EC until the engine uses them).
- [x] `openplantbook.py`: OAuth2 client credentials, token cache, search, detail, error and rate-limit handling
  - Endpoints checked against the official SDK (`slaxor505/openplantbook-sdk-py`): `POST /token/` (form data), `GET /plant/search?alias=`, `GET /plant/detail/{pid}/`.
  - `OpenPlantbookClient(session, client_id, client_secret)`: `async_authenticate` (credential check for the flow), `async_search` → `SpeciesMatch`, `async_get_profile` → `SpeciesProfile`. Token kept in memory, renewed 5 min before expiry and once on HTTP 401.
  - Errors: `OpenPlantbookAuthError` (token 400/401/403, API 403, repeated 401), `OpenPlantbookRateLimitError` (429), otherwise `OpenPlantbookError` (network, timeout, other HTTP, bad JSON). The client does not log; callers decide.
- [x] Client tests with `aioclient_mock`
  - The `client` fixture must depend on `aioclient_mock`, or the HA session is created unmocked. `mypy` ignores missing types of `pytest_homeassistant_custom_component`.

## Phase 3. Integration: flows and devices
- [x] Hub `ConfigFlow`: OpenPlantbook credentials (validated), default weather entity; single instance
  - Single instance via `"single_config_entry": true` in the manifest (no check in the flow). Data: `client_id`, `client_secret`, optional `weather_entity`. Errors: `invalid_auth`, `rate_limited`, `cannot_connect`, `unknown`; entered values are kept on error.
  - Minimal `async_setup_entry` / `async_unload_entry` (no-op) so the created entry loads; runtime data arrives with the coordinator.
  - Hub step strings in en/ru; the OpenPlantbook URL is a description placeholder (hassfest rejects URLs in translations). hassfest passes locally (`docker run --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest`).
- [x] Hub options/reconfigure
  - `reconfigure` step only, no options flow: the hub has just three settings and credentials must be re-checked anyway. Same form as `user`, prefilled; saves with `async_update_reload_and_abort(data=...)` (full replace, so clearing the weather entity removes it).
- [x] `PlantSubentryFlow.user`: name, species search, `location_type`, area, soil sensor, intervals
  - Two steps (maintainer's choice): `user` = name + optional search text; `details` = species dropdown (only after a search; empty = no species), location (default indoor), area, soil moisture sensor, per-plant weather override, watering/feeding intervals (defaults 7 / 30 d).
  - Search errors (`invalid_auth`, `rate_limited`, `cannot_connect`, field error `no_species_found`) keep the user on step one; clearing the search continues without a species.
  - A subentry flow cannot learn its new `subentry_id`, so the area travels as a one-time `area_id` key in the subentry data; device creation (next tasks) must apply it and remove the key.
  - Species range overrides are left to `reconfigure`. `config_flow.py` is at 270 lines: move `PlantSubentryFlow` to `plant_flow.py` when adding `reconfigure`.
- [x] `PlantSubentryFlow.reconfigure`
  - Same two steps as adding: `reconfigure` (name prefilled, optional new search) → `reconfigure_details` (prefilled; no area, since the plant moves with its device; plus species range overrides `min/max_temp`, `min/max_env_humid`, `min/max_soil_moist`). A minimum above its maximum is `invalid_range`.
  - Species: no new search keeps it; after a search the dropdown decides, and leaving it empty removes the species. A pending `area_id` handoff is carried over. Saves with `async_update_reload_and_abort` (full replace, so cleared fields disappear).
  - `PlantSubentryFlow` moved to `plant_flow.py`; flow helpers shared with the hub flow live in `flow_helpers.py`.
- [x] Device per subentry with area; deleting a subentry removes the device and history
  - `devices.py`: on setup, one device per plant (`identifiers={(DOMAIN, subentry_id)}`, bound to the subentry, named after it); a pending `area_id` is applied if the area exists and always removed from the data.
  - The entry has an update listener that reloads it, so added, edited and removed plants apply at once. Consequence: both reconfigure flows use `async_update_and_abort` (a subentry's `async_update_reload_and_abort` raises with an update listener).
  - HA deletes a removed subentry's device itself; setup prunes CareLog history of plants that no longer exist (also covers deletions while HA was down).
  - `runtime.py`: `PlantCareRuntimeData` (care log for now), `PlantCareConfigEntry`.
- [x] en/ru translations for all flows
  - Strings were written with each flow; this task added `tests/test_translations.py` as a guard: `en.json` equals `strings.json`, `ru.json` has exactly the same keys and placeholders, and every form field of every flow step (driven through the real flows) has a label. Each check was mutation-tested.

## Phase 4. Climate and coordinator
- [x] `ClimateResolver`: area sensors (entity area or its device's area), median, ignore unavailable
  - Plain functions in `climate.py` for now: `async_indoor_sources(hass, area_id)` → `IndoorSources` (sorted temperature/humidity entity ids, `entity_ids` for subscriptions) and `read_indoor(hass, sources, soil_entity)` → `ClimateReading`. A class only if the outdoor forecast cache needs one.
  - Device class: the user's override wins over the original; disabled entities are skipped. Temperatures are converted to °C (species ranges are in °C); unknown units and non-finite values are skipped.
- [x] `ClimateResolver`: weather + `weather.get_forecasts` for outdoor
  - `climate.read_outdoor(hass, weather_entity, soil_entity)`: temperature (to °C) and humidity from the weather entity's attributes.
  - `rain.py` `RainTracker`: daily forecast (hourly fallback, summed per local day), converted to mm, fetched at most once per hour per entity. Weather entities only forecast, so a day keeps its last forecast once it has passed (14 days kept): that approximates past rain. Fetch errors are logged; known days are kept.
  - In memory only: after a restart past rain is unknown until it is forecast again (Backlog).
- [x] React to device area changes (`EVENT_DEVICE_REGISTRY_UPDATED`) → rebuild subscriptions
  - Done together with the coordinator (the subscriptions are its own). Any device area change and any entity registry change of area, device, device class or enabled state triggers an immediate refresh, which re-resolves sources and rebuilds the state subscription. Moving a sensor counts, not only moving the plant.
- [x] `DataUpdateCoordinator`: timer + state events + CareLog events
  - `PlantCareCoordinator` (`coordinator.py`) + `plants.py` (subentry → `PlantConfig`, profile + overrides). 30 min timer; source state changes are debounced; `async_log_care(event)` stores and refreshes (for phase 5 buttons/actions).
  - Species profile refetched when stale; on failure the cache is used and the retry waits 1 h, so an offline OpenPlantbook never blocks setup.
- [x] Clean entry unload (all listeners removed)
  - Base coordinator shuts down with the entry; `async_shutdown` closes the state subscription; registry listeners use `entry.async_on_unload`. A test counts open state subscriptions (mutation-checked: dropping the unsubscribe fails it).

## Phase 5. Entities and actions
- [x] `entity.py`: base class with `device_info` and `unique_id`
  - `PlantCareEntity` (`CoordinatorEntity`): `has_entity_name`, `translation_key` = key, `unique_id` = `{subentry_id}_{key}`, device by identifier; `plan` property; unavailable without a plan. Built and tested together with the sensors.
- [x] `sensor`: next/last watering/feeding, statuses
  - Description-driven (`value_fn` / `attributes_fn`); added per plant with `config_subentry_id`. `watering_status` carries `climate_status` and `explanation` (unrecorded: it changes every update). en/ru names, enum states, attribute labels; `icons.json` with state icons.
- [x] `binary_sensor`: needs_water, needs_feeding
  - On while the matching status is `due` or `overdue` (`soon` stays off); unknown while nothing is scheduled. No device class; states translated Yes/No (en) and Да/Нет (ru), `on` state icons.
- [x] `button`: water, feed
  - A press logs the care at `utcnow()` through `coordinator.async_log_care`. The Ficus test hub moved to `tests/conftest.py` as `plant_entry`.
- [x] Actions `water`, `feed`, `move`, `refresh_species` + `services.yaml` + translations
  - One required `device_id` per call (device selector filtered to `plant_care`, as core integrations do), not a `target`. Each call checks the device is a plant of the loaded hub (`plant_not_found`, `hub_not_loaded`). `when` without a zone is local time; future times are `when_in_future`. `refresh_species` goes through `coordinator.async_refresh_species`, which also clears the fetch-retry pause.
- [x] Diagnostics (`diagnostics.py`) without secrets
  - Config entry diagnostics: hub data with `client_id`/`client_secret` redacted; per plant its title, area, subentry data, care log and plan; cached profiles of the species in use. `species_entry` test fixture moved to `tests/conftest.py`.

## Phase 6. Live HA check and release
- [ ] Manual run on a test HA: add 2 indoor + 1 outdoor plant, move one, log a watering
- [x] Automation examples ("time to water" notification) in README
  - Four examples: notify per plant (`mode: parallel`), morning summary via a binary sensor group helper, actionable notification and NFC tag that press the plant's `water` button (entity-based, since the actions take `device_id`). `tests/test_readme.py` loads every example as an automation.
- [x] Friendlier README: My Home Assistant buttons (open in HACS, add integration), badges, emojis
  - `tests/test_readme.py` finds the examples section by "Automation examples" without the `## ` prefix, so the heading can carry an emoji.
- [ ] Calibrate factors against real data
- [ ] Choose a license
- [ ] Brand assets (icon/logo) and drop `ignore: brands` from the HACS job in CI
- [ ] First release v0.1.0 (HACS custom repository)

## Phase 7. Data for the Lovelace cards (`shipulinlev/ha-plants-care-card`)
Additive only: existing entities, unique IDs and automations stay as they are; the cards hide missing fields.
- [x] Species name as the plant device's `model` (OpenPlantbook `display_pid`; `None` without a species)
  - The name lives in the profile cache (`SpeciesProfile.display_pid`), not the subentry. Profile cache storage v2: v1 profiles are kept but marked stale, so existing plants get their name on the next refresh. The model falls back to `species_pid` while no name is cached; it is set at setup and after every coordinator refresh (`async_update_species_models`).
- [x] `interval_days` attribute on `next_watering` (after the climate multiplier) and `next_feeding` (after the season factor)
  - `CarePlan.watering_interval` / `feeding_interval`. The engine always knows both (initial interval before history, season factor before the first feeding), so the attribute is present whenever there is a plan; rounded to 2 decimals so tiny climate changes don't add recorder rows. Diagnostics show them as HA's extended-JSON `timedelta` (`total_seconds`).
- [ ] `entity_picture` on `next_watering` from the OpenPlantbook profile's `image_url`

## Backlog / ideas (after v0.1)
- Persist `RainTracker` days in a `Store`, so past rain survives an HA restart (today it is lost and an outdoor plant may show "needs water" right after rain)
- "Garden" Lovelace card via websocket API
- `calendar` entity with the care schedule
- Light levels (`min/max_light_lux`) and placement recommendations
- Repotting, misting, other care types
- Plant import and export
- Calibrate engine defaults (rain threshold, seasonal factors, soon/overdue windows) on real use; maybe a winter feeding pause option

## Decision log
Short index of decisions. When a decision needs a full ADR in `docs/adr/`, link it from its row.

| Date | Decision | Reason |
|---|---|---|
| 2026-09-29 | Custom integration, not an add-on | Native access to areas, devices, entities and actions; works on every HA install type |
| 2026-09-29 | Plant = config subentry + device | Standard CRUD in the UI without a custom frontend; the device registry provides areas and moving |
| 2026-09-29 | Area stored only in the device registry | Single source of truth; moving uses standard HA tools |
| 2026-09-29 | Species norms from OpenPlantbook, intervals from user history | OpenPlantbook only provides environment ranges, no watering or feeding intervals |
| 2026-09-29 | Indoor: area sensors; outdoor: weather + precipitation | User requirement (garden and balcony) |
| 2026-09-29 | Engine in `core/` with no HA dependency | Fast deterministic unit tests, easy calibration |
| 2026-09-29 | Domain `plant_care` | No clash with the built-in `plant` integration |
| 2026-09-29 | Dev container as the primary environment | HA cannot run natively on Windows; a container is closest to the real HA runtime |
| 2026-09-29 | Python 3.14, dev dependencies via PEP 735 `[dependency-groups]` | HA 2026.9 requires Python ≥ 3.14.2; the integration is not installed as a package, so `pyproject.toml` is tooling-only |
| 2026-09-29 | All repo content in English; `PLAN.md` is the roadmap, GitHub Issues hold tickets | Maintainer's choice; agent skills expect a GitHub issue tracker |
| 2026-09-29 | Minimum HA version 2026.8.0 | Needs config subentries and the single-config-entry device registry API (2026.8) |
| 2026-09-29 | Engine defaults live in `EngineSettings`; no schedule without an anchor event | One place to calibrate; a new plant should not claim "needs water" before anything is known |
| 2026-09-29 | `explanation` is English technical text, not translated | Attribute values cannot use HA translations; it is a debugging aid |
| 2026-09-29 | Project is openly AI-assisted ("vibe coded") | Transparency for users; disclaimer in README |
| 2026-10-02 | `CLAUDE.md` holds only workflow, cross-cutting rules and pointers; domain and HA details live in `docs/` | Progressive disclosure: a task loads only the docs for the area it touches; maintainer's request |
| 2026-10-01 | Plant flow: search, then pick species | Maintainer's choice; no need to look up PIDs by hand, and a plant can still be added when OpenPlantbook is down |
| 2026-10-01 | Area passed as a one-time `area_id` in subentry data, removed once applied to the device | HA generates the `subentry_id` after the flow finishes, so the flow cannot write the device area itself; the device registry stays the only lasting home of the area |
| 2026-10-01 | Flow schemas use `voluptuous`, not `probatio` | Current developer docs show `probatio`, but HA 2026.9.4 (our pin) types `FlowHandler` with `vol.Schema` and no core flow uses `probatio` yet; revisit when the pin is bumped |
| 2026-10-17 | Species display name kept in the profile cache, not in subentry data | One source for everything OpenPlantbook says about a species; existing plants get the name without a migration of their subentries, and `refresh_species` updates it |
