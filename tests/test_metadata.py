"""The integration's JSON files agree with each other.

A mistyped key in icons.json or translations is silently ignored by Home
Assistant, so these catch it here instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

INTEGRATION = Path(__file__).parents[1] / "custom_components" / "sonnen_battery"


def _load(name: str) -> dict:
    return json.loads((INTEGRATION / name).read_text(encoding="utf-8"))


def test_translations_match_strings() -> None:
    assert _load("translations/en.json") == _load("strings.json")


def test_icons_refer_to_real_entities_and_states() -> None:
    strings = _load("strings.json")["entity"]
    for platform, entities in _load("icons.json")["entity"].items():
        for key, icon in entities.items():
            assert key in strings[platform], f"icons.json: unknown {platform} '{key}'"
            states = strings[platform][key].get("state")
            for state in icon.get("state", {}):
                if platform != "binary_sensor":  # on/off come from Home Assistant
                    assert state in states, f"icons.json: unknown state '{state}' for {key}"


def test_icons_cover_every_action() -> None:
    services = yaml.safe_load((INTEGRATION / "services.yaml").read_text(encoding="utf-8"))
    assert set(_load("icons.json")["services"]) == set(services)


def test_quality_scale_lists_every_rule_once() -> None:
    rules = yaml.safe_load((INTEGRATION / "quality_scale.yaml").read_text(encoding="utf-8"))["rules"]
    for name, value in rules.items():
        status = value["status"] if isinstance(value, dict) else value
        assert status in {"done", "todo", "exempt"}, name
        if status == "exempt":
            assert value.get("comment"), f"{name}: exempt rules need a comment"
    assert len(rules) == 54  # the rule count in hassfest as of Home Assistant 2026.10
