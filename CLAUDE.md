# CLAUDE.md

**Plant Care** is a Home Assistant custom integration (`custom_components/plant_care`, distributed via HACS): plants are config subentries of one hub, each with its own device; a plant's room is its device's area; watering and feeding are scheduled from climate (room sensors indoors, weather outdoors), the user's care history and OpenPlantbook species ranges. It is neither a Supervisor add-on nor the built-in `plant` integration. Out of scope: a custom frontend, irrigation hardware, photo recognition.

Claude writes most of the code; the maintainer steers and reviews. Leave the repo so the next session can resume from `PLAN.md` and this file.

## Workflow
`PLAN.md` is the single source of truth for status. Update it as you go:

1. Before starting: read `PLAN.md` for the current phase and next step, then the docs below for the area you will touch.
2. Starting a task: mark it `[~]`.
3. Test first: write the test, watch it fail for the right reason, then write the minimal code.
4. **Done** means `scripts/test` is green (ruff check, ruff format --check, mypy strict, pytest). Only then mark the task `[x]`, with a short note on anything decided along the way.
5. Found a new task, bug or debt: add it to its phase or to "Backlog". Changed a decision: update the "Decision log" in `PLAN.md` and the doc that describes it.
6. Commit only when the user asks: one `PLAN.md` task per commit, Conventional Commits (`feat(engine): ...`).

## Rules
- Everything is in English (code, comments, docs) except UI translations in `translations/ru.json`.
- `core/` and `tests/core/` stay pure Python with no `homeassistant` imports (ruff `TID251`); the engine gets the current time as a parameter.
- Python 3.14, full type hints, mypy strict. Annotations are lazy (PEP 649), so `from __future__ import annotations` is unneeded.
- Small single-purpose modules; past ~300 lines, split. YAGNI: extension points are described in `PLAN.md`, not built.
- The HA version is pinned by `pytest-homeassistant-custom-component` in `pyproject.toml`; bump it deliberately and note it in `PLAN.md`. Verify HA APIs against that version, not memory.
- The user's own HA (HA MCP tools): read freely; change it only with their explicit consent.

## Docs
Read the matching doc before working in an area:

| Doc | Read when |
|---|---|
| `docs/development.md` | running tests or HA, using the dev container, hitting a Windows host quirk |
| `docs/ha-integration.md` | writing integration code outside `core/`: HA conventions, flows, strings, verified APIs |
| `docs/testing.md` | writing or fixing tests |
| `docs/architecture/data-model.md` | hub, plants, subentry data, devices, rooms (areas), the flows |
| `docs/architecture/engine.md` | scheduling logic in `core/` |
| `docs/architecture/climate.md` | climate sources (`ClimateResolver`) |
| `docs/architecture/openplantbook.md` | species profiles, the OpenPlantbook client, the profile cache |
| `docs/architecture/care-log.md` | care history storage |
| `docs/architecture/coordinator.md` | the coordinator and its update triggers |
| `docs/architecture/entities-and-actions.md` | entities, actions (services), README automation examples |
| `docs/agents/issue-tracker.md` | GitHub issues (`shipulinlev/ha-plant-care`, via `gh`); `PLAN.md` references them as `#N` |
| `docs/agents/triage-labels.md` | triage labels |
| `docs/agents/domain.md` | the domain glossary (`CONTEXT.md`) and ADRs (`docs/adr/`) |

`README.md` is user-facing documentation.
