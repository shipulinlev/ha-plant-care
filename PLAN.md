# PLAN.md — roadmap and progress

Statuses: `[ ]` not started · `[~]` in progress · `[x]` done (tests, ruff and mypy green) · `[-]` dropped.
Update rules are in `CLAUDE.md` ("Mandatory rule: PLAN.md"). Items tracked as GitHub issues carry the reference: `(#N)`.

**Current phase:** 0. Project scaffolding
**Next step:** CI (GitHub Actions); `gh` CLI setup is pending on the maintainer

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
- [ ] Install and authenticate the `gh` CLI (needed by the issue-tracker skills)
- [x] Skeleton of `custom_components/plant_care/`: `manifest.json`, `const.py`, `__init__.py`, `hacs.json`
  - `__init__.py` has `CONFIG_SCHEMA = config_entry_only_config_schema` (UI-only) and a no-op `async_setup` (actions will be registered there).
  - `manifest.json`: `config_flow: false` until phase 3; `integration_type: hub`, `iot_class: cloud_polling` (OpenPlantbook).
  - Tests: `tests/test_init.py` (manifest discovery, setup); `pythonpath = ["."]` in pytest config; `tests/core/conftest.py` overrides the HA autouse fixture so core tests run on Windows.
- [x] Pin the minimum HA version: `2026.8.0` in `hacs.json` (`manifest.json` has no min-version field for custom integrations)
  - Correction: the single-config-entry-per-device change landed in HA **2026.8**, not 2026.07 (developers blog 2026-07-21).
- [~] CI (GitHub Actions): pytest, ruff, mypy, hassfest, HACS validation

## Phase 1. Core: models and engine (no HA, TDD)
- [ ] `core/models.py`: `PlantConfig`, `SpeciesProfile`, `CareEvent`, `ClimateReading`, `CarePlan`, status enums
- [ ] Base watering interval: median of the last N intervals, fallback to `initial_watering_interval_days`
- [ ] Climate multiplier from temperature and humidity relative to the species range, clamped to 0.5–1.5
- [ ] Precipitation handling for outdoor plants
- [ ] Soil moisture sensor priority
- [ ] Feeding: interval + seasonal factor (hemisphere from latitude)
- [ ] `ok/soon/due/overdue` statuses and `explanation`
- [ ] Edge cases: no history, no climate, no species profile, future events, duplicate events

## Phase 2. Storage and external data
- [ ] `storage.py`: `CareLog` on `Store` (version, migrations, deleting a plant's history)
- [ ] `storage.py`: OpenPlantbook profile cache with TTL
- [ ] `openplantbook.py`: OAuth2 client credentials, token cache, search, detail, error and rate-limit handling
- [ ] Client tests with `aioclient_mock`

## Phase 3. Integration: flows and devices
- [ ] Hub `ConfigFlow`: OpenPlantbook credentials (validated), default weather entity; single instance
- [ ] Hub options/reconfigure
- [ ] `PlantSubentryFlow.user`: name, species search, `location_type`, area, soil sensor, intervals
- [ ] `PlantSubentryFlow.reconfigure`
- [ ] Device per subentry with area; deleting a subentry removes the device and history
- [ ] en/ru translations for all flows

## Phase 4. Climate and coordinator
- [ ] `ClimateResolver`: area sensors (entity area or its device's area), median, ignore unavailable
- [ ] `ClimateResolver`: weather + `weather.get_forecasts` for outdoor
- [ ] React to device area changes (`EVENT_DEVICE_REGISTRY_UPDATED`) → rebuild subscriptions
- [ ] `DataUpdateCoordinator`: timer + state events + CareLog events
- [ ] Clean entry unload (all listeners removed)

## Phase 5. Entities and actions
- [ ] `entity.py`: base class with `device_info` and `unique_id`
- [ ] `sensor`: next/last watering/feeding, statuses
- [ ] `binary_sensor`: needs_water, needs_feeding
- [ ] `button`: water, feed
- [ ] Actions `water`, `feed`, `move`, `refresh_species` + `services.yaml` + translations
- [ ] Diagnostics (`diagnostics.py`) without secrets

## Phase 6. Live HA check and release
- [ ] Manual run on a test HA: add 2 indoor + 1 outdoor plant, move one, log a watering
- [ ] Automation examples ("time to water" notification) in README
- [ ] Calibrate factors against real data
- [ ] Choose a license
- [ ] Brand assets (icon/logo) and drop `ignore: brands` from the HACS job in CI
- [ ] First release v0.1.0 (HACS custom repository)

## Backlog / ideas (after v0.1)
- "Garden" Lovelace card via websocket API
- `calendar` entity with the care schedule
- Light levels (`min/max_light_lux`) and placement recommendations
- Repotting, misting, other care types
- Plant import and export

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
| 2026-09-29 | Project is openly AI-assisted ("vibe coded") | Transparency for users; disclaimer in README |
