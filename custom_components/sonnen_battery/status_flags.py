"""Decoding the status flags in /api/v2/latestdata (`ic_status`).

The battery reports each group as {"Flag name": true/false, ...}, with at most
one flag set. No Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

from typing import Any

# Eclipse LED (the light ring on the front) -> sensor option.
LED_STATES = {
    "Pulsing White": "pulsing_white",
    "Pulsing Green": "pulsing_green",
    "Pulsing Orange": "pulsing_orange",
    "Solid Red": "solid_red",
    "Blinking Red": "blinking_red",
}
LED_OFF = "off"
LED_OPTIONS = [*LED_STATES.values(), LED_OFF]
RED_LED = {"solid_red", "blinking_red"}

# DC shutdown reasons that mean something is wrong with the battery, as
# opposed to normal ones such as reaching the minimum charge.
FAULT_FLAGS = (
    "Critical BMS Alarm",
    "Electrolyte Leakage",
    "HW_Shutdown",
    "Inverter Over Temperature",
)

NO_SHUTDOWN = "none"


def _group(ic_status: dict[str, Any], name: str) -> dict[str, Any] | None:
    group = ic_status.get(name)
    return group if isinstance(group, dict) else None


def status_led(ic_status: dict[str, Any]) -> str | None:
    if (led := _group(ic_status, "Eclipse Led")) is None:
        return None
    for flag, option in LED_STATES.items():
        if led.get(flag) is True:
            return option
    return LED_OFF


def shutdown_reason(ic_status: dict[str, Any]) -> str | None:
    if (reasons := _group(ic_status, "DC Shutdown Reason")) is None:
        return None
    return next((flag for flag, on in reasons.items() if on is True), NO_SHUTDOWN)


def has_problem(ic_status: dict[str, Any]) -> bool | None:
    """True if the LED shows red or a fault flag is set; None without data."""
    led = status_led(ic_status)
    reasons = _group(ic_status, "DC Shutdown Reason")
    if led is None and reasons is None:
        return None
    return led in RED_LED or any((reasons or {}).get(flag) is True for flag in FAULT_FLAGS)
