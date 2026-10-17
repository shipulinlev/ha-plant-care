# Species profiles: OpenPlantbook client and cache

Modules: `openplantbook.py` (`OpenPlantbookClient`), `storage.py` (`ProfileCache`), `flow_helpers.py` (client from hub data, error → form error key).

**OpenPlantbook provides environment ranges only, never watering or feeding intervals.** Intervals come from the user's settings and care history.

## API client
- Endpoints (checked against the official SDK `slaxor505/openplantbook-sdk-py`): `POST /api/v1/token/` (form data, OAuth2 client credentials), `GET /plant/search?alias=`, `GET /plant/detail/{pid}/`.
- Session from `async_get_clientsession`. The token is kept in memory, renewed 5 min before expiry and once more on HTTP 401.
- Methods: `async_authenticate` (credential check for the hub flow), `async_search` → `SpeciesMatch`, `async_get_profile` → `SpeciesProfile` (the six ranges plus the readable `display_pid`, `None` when missing).
- Errors: `OpenPlantbookAuthError` (token 400/401/403, API 403, repeated 401), `OpenPlantbookRateLimitError` (429), otherwise `OpenPlantbookError` (network, timeout, other HTTP, bad JSON). The client never logs; callers decide.
- Detail also has `min/max_light_lux` and `min/max_soil_ec`; they are not mapped until the engine uses them.

## Profile cache
- `ProfileCache` on a `Store` (`plant_care.species_profiles`, version 2), TTL 30 days.
- Version 2 added `display_pid`. The migration keeps version 1 profiles but marks them fetched long ago, so the next refresh fetches the name while an offline upgrade still has the old ranges.
- `get` serves a profile of any age so the integration works offline; `needs_refresh` tells the caller when to refetch; `async_remove` backs `plant_care.refresh_species`.
- Plant range overrides take precedence over cached API values.

## Error handling
- In flows: a clear form error (keys from `form_error_key`).
- At runtime: log and keep working from the cache. An unreachable OpenPlantbook with a cached profile never raises `ConfigEntryNotReady`.
