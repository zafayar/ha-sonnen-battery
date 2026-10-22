"""Decoding the latestdata status flags."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.sonnen_battery.status_flags import has_problem, shutdown_reason, status_led

from .conftest import load_fixture


@pytest.fixture
def ic_status() -> dict[str, Any]:
    return load_fixture("latestdata.json")["ic_status"]


def test_healthy_battery(ic_status: dict[str, Any]) -> None:
    assert status_led(ic_status) == "pulsing_white"
    assert shutdown_reason(ic_status) == "none"
    assert has_problem(ic_status) is False


@pytest.mark.parametrize("led", ["Solid Red", "Blinking Red"])
def test_red_light_is_a_problem(ic_status: dict[str, Any], led: str) -> None:
    ic_status["Eclipse Led"]["Pulsing White"] = False
    ic_status["Eclipse Led"][led] = True
    assert has_problem(ic_status) is True


@pytest.mark.parametrize("flag", ["Critical BMS Alarm", "Electrolyte Leakage", "HW_Shutdown"])
def test_fault_flag_is_a_problem(ic_status: dict[str, Any], flag: str) -> None:
    ic_status["DC Shutdown Reason"][flag] = True
    assert shutdown_reason(ic_status) == flag
    assert has_problem(ic_status) is True


def test_normal_shutdown_is_not_a_problem(ic_status: dict[str, Any]) -> None:
    ic_status["DC Shutdown Reason"]["Minimum rSOC of System reached"] = True
    assert shutdown_reason(ic_status) == "Minimum rSOC of System reached"
    assert has_problem(ic_status) is False


def test_light_off(ic_status: dict[str, Any]) -> None:
    ic_status["Eclipse Led"]["Pulsing White"] = False
    assert status_led(ic_status) == "off"


def test_missing_data() -> None:
    assert status_led({}) is None
    assert shutdown_reason({"DC Shutdown Reason": "garbage"}) is None
    assert has_problem({}) is None
