# Climate sources (`climate.py`)

`climate.py` resolves readings for the engine. It is not the HA `climate` platform; that platform is never registered.

## Indoor
- `async_indoor_sources(hass, area_id)` → `IndoorSources`: `sensor` entities in the plant's area with device class `temperature` / `humidity` (the user's device class override wins over the original). An entity's own area wins; without one, its device's area counts. Disabled entities are skipped. `entity_ids` lists every source for state subscriptions.
- `read_indoor(hass, sources, soil_moisture_entity)` → `ClimateReading`: median per quantity; `unavailable`, `unknown`, non-numeric and non-finite states are skipped. Temperatures are converted to °C, the unit of the species ranges.
- No area, or no usable sensor, gives `None` values.

## Outdoor
- A `weather` entity: the plant's override, else the hub default. Current temperature and humidity from its attributes; precipitation from the forecast via the `weather.get_forecasts` action (`return_response`), aggregated per day before it reaches the engine.

## Both
- The plant's **soil moisture sensor**, when set, is read wherever it is and takes priority in the engine.
- Missing data is not an error: the engine falls back to the base interval with `climate_status = unknown`.
- Sources are re-resolved when a plant's device area changes (see `data-model.md`).
