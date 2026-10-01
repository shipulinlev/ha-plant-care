# CLAUDE.md

Guidance for Claude Code when working in this repository. User-facing docs live in `README.md`; the roadmap and progress log live in `PLAN.md`.

This project is built with AI assistance ("vibe coding"): Claude Code writes most of the code, the maintainer steers and reviews. Keep that in mind: leave the repo in a state where the next session can pick up from `PLAN.md` and this file alone.

## Mandatory rule: PLAN.md

`PLAN.md` is the single source of truth for development status. **Update it as you go, not at the end:**

- starting a task: mark it `[~]` (in progress);
- finished and verified (tests green): mark it `[x]` and add a short note if something was decided or changed along the way;
- new task, bug or tech debt discovered: add an item to the relevant phase or to the "Backlog" section;
- an architectural decision changed: update the "Decision log" in `PLAN.md` and the matching section of this file;
- before starting work: read `PLAN.md` to learn the current phase and the next step.

A task may not be marked `[x]` unless `pytest`, `ruff` and `mypy` pass for it.

## What this project is

**Plant Care** is a Home Assistant custom integration (`custom_components/plant_care`, distributed via HACS). It is **not** a Supervisor add-on and **not** the built-in `plant` integration.

Features:
1. Plant CRUD through the standard HA UI ("Devices & services").
2. Assigning a plant to a room (HA area) and moving it between rooms.
3. Estimating and scheduling watering and feeding based on climate: room sensors for indoor plants, weather for garden and balcony plants; plus the care history logged by the user and species norms from OpenPlantbook.

Out of scope (for now): a custom frontend (panel, Lovelace card), controlling irrigation hardware (valves, pumps), plant recognition from photos.

## Architecture

### 1. Data model in HA
- Domain: `plant_care`.
- **Config entry (hub)**, one per installation: OpenPlantbook credentials (`client_id`, `client_secret`) and the default `weather` entity for outdoor plants.
- **Plant = config subentry** of type `plant`. Created through the subentry flow `user` step, edited through `reconfigure`, deleted the standard way.
- **Each plant maps to exactly one device**, bound to the subentry (`config_subentry_id`). All plant entities belong to that device.
- Subentry data: `name`, `species_pid` (OpenPlantbook PID, optional), `location_type` (`indoor` | `outdoor`), `soil_moisture_entity` (optional), `initial_watering_interval_days`, `feeding_interval_days`, species range overrides.

### 2. Room = the device's area
- The area is stored **only** in the device registry and is **not duplicated** in subentry data.
- Moving a plant: the user changes the device area in the standard UI, or calls `plant_care.move`, which does the same.
- The integration listens to `EVENT_DEVICE_REGISTRY_UPDATED` and re-resolves climate sources when the area changes.
- When a plant is created, the area is picked in the subentry flow (`AreaSelector`) and written to the device immediately.

### 3. Climate sources (`climate.py`, `ClimateResolver`)
- **indoor**: `sensor` entities in the plant's area with `device_class` `temperature` / `humidity`. An entity's area comes from the entity registry, falling back to its device's area. With several sensors, take the median. Ignore `unavailable` / `unknown`.
- **outdoor**: a `weather` entity (from the hub, overridable per plant). Current temperature and humidity come from attributes; precipitation from the forecast via the `weather.get_forecasts` action (with `return_response`).
- A plant's **soil moisture sensor**, when set, takes priority over the heuristics.
- Missing data is not an error: the engine falls back to the base interval with `climate_status = unknown`.

### 4. Species profile (`openplantbook.py`, `SpeciesProfile`)
- Async client on `aiohttp` (session from `async_get_clientsession`). Auth: OAuth2 Client Credentials; the token is cached until expiry.
- Endpoints: search (species lookup in the subentry flow) and detail (profile).
- Detail fields: `min/max_temp`, `min/max_env_humid`, `min/max_soil_moist`, `min/max_light_lux`, `min/max_soil_ec`.
- **Important: OpenPlantbook does NOT provide watering or feeding intervals.** It only provides acceptable environment ranges. Intervals come from the user's history and settings.
- Profiles are cached in a `Store` so the integration works offline and stays within API limits. Subentry overrides take precedence over API values.

### 5. Care history (`storage.py`, `CareLog`)
- `watered` / `fed` events with a UTC timestamp and `plant_id` (= `subentry_id`) are stored in a `homeassistant.helpers.storage.Store` with versioning and migrations.
- History is not kept in entity state or in the recorder.
- Events are recorded via `button` entities ("Watered" / "Fed") and the `plant_care.water` / `plant_care.feed` actions (the `when` field allows backdating).
- Deleting a subentry deletes its history.

### 6. Scheduling engine (`core/engine.py`, `CareEngine`)
Pure Python, **no `homeassistant` imports**, deterministic (the current time is passed in as a parameter).
- **Base watering interval** = median of the last N (default 5) intervals in the CareLog. With fewer than 2 intervals, use `initial_watering_interval_days`.
- **Climate multiplier**: how far temperature and humidity fall outside the species range. Hotter or drier than the range → shorter interval; cooler or more humid → longer. The multiplier is clamped (default 0.5–1.5).
- **Outdoor**: past and forecast precipitation shift the watering date (rain ≥ threshold counts as watering). The engine compares each `Precipitation` entry against the threshold as is, so the caller aggregates forecast data per day.
- **Soil sensor**: below `min_soil_moist` → water now; above `max_soil_moist` → no watering needed.
- **Feeding**: user-defined interval times a seasonal factor (meteorological seasons, hemisphere from HA latitude; winter x2, autumn x1.5).
- No logged watering or feeding (and no rain or soil reading to anchor on) → `next_*` and `*_status` are `None`.
- Output (`CarePlan`): `next_watering`, `next_feeding`, `watering_status` / `feeding_status` (`ok` | `soon` | `due` | `overdue`), `climate_status`, `last_watered`, `last_fed`, `explanation` (a short English technical summary of the calculation, exposed as an attribute; not translated).

### 7. Coordinator (`coordinator.py`)
- One `DataUpdateCoordinator` per config entry; it recomputes the `CarePlan` for every plant.
- Triggers: a timer (30 min), state changes of climate entities (`async_track_state_change_event`; subscriptions are rebuilt on area change), new CareLog entries, subentry changes, device area changes.
- Network calls (OpenPlantbook, forecast) are not made on every tick; they are served from cache with their own TTL.

### 8. Plant entities
| Platform | Entity | Purpose |
|---|---|---|
| `sensor` | `next_watering`, `next_feeding` | `device_class: timestamp` |
| `sensor` | `watering_status`, `feeding_status` | `device_class: enum` |
| `sensor` | `last_watered`, `last_fed` | `device_class: timestamp` |
| `binary_sensor` | `needs_water`, `needs_feeding` | for automations and notifications |
| `button` | `water`, `feed` | log care "now" |

All entities: `has_entity_name = True`, `translation_key`, `unique_id = f"{subentry_id}_{key}"`.

### 9. Actions (services)
`plant_care.water`, `plant_care.feed` (target: the plant device, optional `when`), `plant_care.move` (device + `area_id`), `plant_care.refresh_species` (drop the cached profile). Actions are registered in `async_setup`, not in `async_setup_entry`.

## Repository layout

```
custom_components/plant_care/
  __init__.py          # async_setup (actions), async_setup_entry/unload, device registry listener
  manifest.json
  const.py
  config_flow.py       # PlantCareConfigFlow (hub) + PlantSubentryFlow (user / reconfigure)
  coordinator.py
  entity.py            # PlantCareEntity: device_info, unique_id
  sensor.py
  binary_sensor.py
  button.py
  services.py          # action handlers
  services.yaml
  climate.py           # ClimateResolver (not the climate platform: we never register that platform)
  openplantbook.py     # API client
  storage.py           # CareLog + profile cache
  strings.json
  translations/en.json
  translations/ru.json
  core/                # pure logic, never imports homeassistant
    models.py          # dataclasses: PlantConfig, SpeciesProfile, CareEvent, ClimateReading, CarePlan
    engine.py          # CareEngine + EngineSettings (defaults for every tunable)
    history.py         # CareLog events -> deduplicated times, median interval
    climate_factor.py  # temperature/humidity multiplier and climate_status
    season.py          # meteorological season, feeding factor
    status.py          # ok / soon / due / overdue
tests/
  conftest.py          # enables custom integrations for HA tests
  core/                # engine unit tests, no HA
    conftest.py        # overrides the HA-only autouse fixture with a no-op
  test_*.py            # integration tests on pytest-homeassistant-custom-component
hacs.json
pyproject.toml         # ruff, mypy, pytest
```

## Coding rules

### General
- Python 3.14 (HA 2026.9 requires ≥ 3.14.2); full type hints. `from __future__ import annotations` is unnecessary (annotations are lazy in 3.14, PEP 649).
- `mypy` in strict mode for all code (configured in `pyproject.toml`).
- `core/` and `tests/core/` must not import `homeassistant`: enforced by ruff (`TID251`).
- The HA version used for development and tests is set by the `pytest-homeassistant-custom-component` pin in `pyproject.toml`. Bump it deliberately and note it in `PLAN.md`.
- Everything in the repo is in English: code, identifiers, comments, docstrings, and documentation (`README.md`, `CLAUDE.md`, `PLAN.md`, `docs/`). The only non-English content is UI translations (`translations/ru.json`).
- Small single-purpose modules. A file past ~300 lines is a signal to split it.
- No speculative abstractions (YAGNI). Extension points are described in `PLAN.md`, not built into code.

### Home Assistant
- Async only. No blocking I/O in the event loop: HTTP via `aiohttp` from `async_get_clientsession`, files via `Store`.
- Typed config entry: `type PlantCareConfigEntry = ConfigEntry[PlantCareRuntimeData]`; runtime data lives in `entry.runtime_data`, not in `hass.data`.
- Inside the integration a plant is identified by `subentry_id`, never by name or `entity_id`. Automation examples (README) use the plant's entity `entity_id`s, not `device_id`, per HA best practices.
- All UI text (flows, errors, entities, actions) lives in `strings.json` and `translations/*.json`. No hard-coded user-facing strings in code.
- OpenPlantbook network errors: show a clear form error in flows; at runtime, log and keep working from cache. Do not raise `ConfigEntryNotReady` for an unreachable OpenPlantbook when a cache exists.
- Action errors: `ServiceValidationError` with a `translation_key`.
- Time: everything in UTC (`dt_util.utcnow()`); local time only for display.
- Logging via `_LOGGER = logging.getLogger(__name__)`; never log secrets.

### Current HA APIs (verified, 2026)
- Subentries: `ConfigFlow.async_get_supported_subentry_types()` → `{"plant": PlantSubentryFlow}`; in `reconfigure` use `self._get_entry()` and `self._get_reconfigure_subentry()`.
- Since HA 2026.8 a device has exactly one config entry (hence the minimum version 2026.8.0 in `hacs.json`): read `device.config_entry_id` / `device.config_subentry_id`; `device.config_entries_subentries` is **deprecated**. Move a device with `async_update_device(new_config_entry_id=..., new_config_subentry_id=...)`.
- Flow and service schemas: `voluptuous` (`import voluptuous as vol`). The developer docs already show `probatio`, but HA 2026.9 still types its flow API with `vol.Schema`; switch only after bumping the HA pin to a version that accepts `probatio`.
- When unsure about an HA API, check current docs (context7: `/home-assistant/developers.home-assistant`) rather than memory.

### Testing (TDD)
- Test first, then implementation. Especially for `core/engine.py`: every factor and edge case is covered by a test.
- `tests/core/` does not use HA and runs fast. Any new autouse fixture in `tests/conftest.py` that needs HA must get a no-op override in `tests/core/conftest.py`, or the core tests break on Windows.
- Integration tests: `pytest-homeassistant-custom-component`, the `hass` fixture, `MockConfigEntry` with subentries, `aioclient_mock` for OpenPlantbook, no real network.
- Must cover: config flow and subentry flow (including errors), area change → climate sources re-resolved, actions, entry unload without leaked listeners.

## Development commands

The primary environment is the **dev container** (`.devcontainer/`: Python 3.14, venv at `/home/vscode/.venv`, port 8123). HA cannot run natively on Windows (`homeassistant/runner.py` imports `fcntl`), so integration tests and a live HA run only inside the container.

```bash
# Start the container (VS Code: "Reopen in Container"; from a terminal:)
npx -y @devcontainers/cli up --workspace-folder .

# Inside the container
scripts/setup      # venv + dev dependencies (runs automatically on create)
scripts/test       # ruff check, ruff format --check, mypy, pytest; extra args go to pytest
scripts/develop    # live HA at http://localhost:8123, loading the integration straight from custom_components/
```

Running a command in the container from the Windows host (Git Bash; `MSYS_NO_PATHCONV=1` is required, otherwise `/workspaces/...` paths get mangled):

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/ha-plants <container_id> scripts/test
# container_id: docker ps --filter label=devcontainer.local_folder --format '{{.ID}}'
```

On Windows without the container, ruff, mypy and the fast engine tests work:

```bash
py -3.14 -m venv .venv && source .venv/Scripts/activate && pip install --group dev
pytest tests/core -q -p no:homeassistant
ruff check . && ruff format --check . && mypy .
```

**Live HA (`scripts/develop`):** config comes from `config/` (git-ignored). On first run `.devcontainer/configuration.yaml` is copied there. It has no `default_config`: its `go2rtc` dependency needs a binary the container does not ship. Add any other HA integration you need to that template explicitly. To read state and logs of the user's own (non-dev) HA, the HA MCP tools can be used (`ha_get_logs`, `ha_get_state`). **Change the user's HA only with their explicit consent.**

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `shipulinlev/ha-plant-care`, via the `gh` CLI; `PLAN.md` stays the roadmap and references issues as `#N`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.

## Git
- Small commits, one `PLAN.md` task each, Conventional Commits style (`feat(engine): ...`).
- Commit only when the user asks.
