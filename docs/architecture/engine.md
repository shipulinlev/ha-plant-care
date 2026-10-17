# Scheduling engine (`core/`)

Pure Python under `custom_components/plant_care/core/`, deterministic: the current time is a parameter. It never imports `homeassistant` (ruff `TID251` enforces this for `core/` and `tests/core/`).

Modules: `models.py` (frozen dataclasses: `PlantConfig`, `SpeciesProfile`, `CareEvent`, `ClimateReading`, `Precipitation`, `CarePlan`, status enums), `engine.py` (`CareEngine`, `EngineSettings`: the single home of every tunable default), `history.py`, `climate_factor.py`, `season.py`, `status.py`.

## Rules
- **Base watering interval** = median of the last N (default 5) intervals in the care history. With fewer than 2 intervals, use `initial_watering_interval_days`. Future events are ignored; events within 6 h of the previous one merge (double button press).
- **Climate multiplier**: how far temperature and humidity fall outside the species range (distance outside / range width). Hotter or drier → shorter interval; cooler or more humid → longer. Clamped to 0.5–1.5 by default. A variable counts only with a reading and both bounds.
- **Outdoor rain**: each `Precipitation` entry ≥ the threshold (default 5 mm) after the last watering and no later than the scheduled date counts as a watering and restarts the interval. The engine compares entries as given, so the caller aggregates forecasts per day.
- **Soil sensor** wins over the estimate: below `min_soil_moist` → water now (keeps `overdue` if already overdue); above `max_soil_moist` → `ok`, next no earlier than now + 1 d. Ignored without the species soil range.
- **Feeding** = user interval × seasonal factor (meteorological seasons, hemisphere from HA latitude; spring/summer ×1, autumn ×1.5, winter ×2).
- **Statuses**: `soon` within 1 d before the date, `due` from the date, `overdue` from 1 d after.
- No logged watering or feeding and no rain or soil reading to anchor on → `next_*` and `*_status` are `None`.
- **Output** (`CarePlan`): `next_watering`, `next_feeding`, `watering_interval` (base interval × climate multiplier, before rain and soil adjustments; known even before the first watering), `feeding_interval` (user interval × season factor, known even before the first feeding), `watering_status` / `feeding_status` (`ok` | `soon` | `due` | `overdue`), `climate_status` (`ok` | `out_of_range` | `unknown`), `last_watered`, `last_fed`, `explanation` (short English technical text, exposed as an attribute, never translated).
- Missing climate data is not an error: base interval with `climate_status = unknown`.

## Tests
Every factor and edge case has a test in `tests/core/`. These run without HA, also on Windows (see `docs/testing.md`).
