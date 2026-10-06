"""The README automation examples stay valid automations."""

from pathlib import Path
import re
from typing import Any

from homeassistant.components.automation.const import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ENTITY_MATCH_ALL,
    SERVICE_TURN_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import parse_yaml

README = Path(__file__).parents[1] / "README.md"
YAML_BLOCK = re.compile(r"```yaml\n(.*?)```", re.S)


def _examples() -> list[dict[str, Any]]:
    text = README.read_text("utf-8")
    section = text.split("## Automation examples", 1)[1].split("\n## ", 1)[0]
    examples: list[dict[str, Any]] = []
    for block in YAML_BLOCK.findall(section):
        example = parse_yaml(block)
        assert isinstance(example, dict)
        examples.append(example)
    return examples


async def test_readme_examples_load(hass: HomeAssistant) -> None:
    """Every example passes HA's automation validation and is enabled."""
    examples = _examples()
    assert len(examples) == 4

    assert await async_setup_component(
        hass, AUTOMATION_DOMAIN, {AUTOMATION_DOMAIN: examples}
    )
    await hass.async_block_till_done()

    states = hass.states.async_all(AUTOMATION_DOMAIN)
    assert sorted(state.name for state in states) == sorted(
        example["alias"] for example in examples
    )
    assert all(state.state == STATE_ON for state in states)
    # Detach the triggers (the morning summary's time trigger is a timer).
    await hass.services.async_call(
        AUTOMATION_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: ENTITY_MATCH_ALL},
        blocking=True,
    )
