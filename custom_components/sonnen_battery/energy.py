"""Turning the battery's live power readings into energy counters.

The sonnen API reports power (W) with signed values, but the Home Assistant
Energy dashboard needs cumulative energy (kWh) per direction. This module splits
each signed reading into non-negative flows and integrates them over time.

No Home Assistant imports, so it can be tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Flow keys. Each becomes one kWh sensor.
GRID_IMPORT = "grid_import"
GRID_EXPORT = "grid_export"
BATTERY_CHARGE = "battery_charge"
BATTERY_DISCHARGE = "battery_discharge"
SOLAR_PRODUCTION = "solar_production"
HOME_CONSUMPTION = "home_consumption"

FLOWS = (
    GRID_IMPORT,
    GRID_EXPORT,
    BATTERY_CHARGE,
    BATTERY_DISCHARGE,
    SOLAR_PRODUCTION,
    HOME_CONSUMPTION,
)

# Longer than this between two readings and we don't guess what happened in
# between: the counter restarts from the next reading instead.
MAX_GAP_SECONDS = 300.0


def to_float(value: Any) -> float | None:
    """API numbers sometimes arrive as strings; anything unusable is None."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None  # NaN -> None


def split_flows(status: dict[str, Any]) -> dict[str, float | None]:
    """Non-negative power (W) per flow from one /api/v2/status reply.

    sonnen's signs: GridFeedIn_W > 0 is export to the grid, < 0 is import.
    Pac_total_W > 0 is the battery discharging, < 0 is charging.
    Production_W can read slightly negative at night; that is treated as 0.
    """
    grid = to_float(status.get("GridFeedIn_W"))
    battery = to_float(status.get("Pac_total_W"))
    production = to_float(status.get("Production_W"))
    consumption = to_float(status.get("Consumption_W"))
    return {
        GRID_IMPORT: None if grid is None else max(-grid, 0.0),
        GRID_EXPORT: None if grid is None else max(grid, 0.0),
        BATTERY_CHARGE: None if battery is None else max(-battery, 0.0),
        BATTERY_DISCHARGE: None if battery is None else max(battery, 0.0),
        SOLAR_PRODUCTION: None if production is None else max(production, 0.0),
        HOME_CONSUMPTION: None if consumption is None else max(consumption, 0.0),
    }


@dataclass
class EnergyIntegrator:
    """A kWh counter fed with (time, watts) readings, trapezoidal rule.

    The total only ever goes up, which is what `total_increasing` requires.
    """

    total_kwh: float = 0.0
    max_gap: float = MAX_GAP_SECONDS
    _last_time: float | None = None
    _last_watts: float | None = None

    def add(self, when: float, watts: float | None) -> float:
        """Record a reading taken at `when` (seconds, monotonic). Returns the total."""
        if watts is None or watts < 0:
            self.reset_baseline()
            return self.total_kwh
        if self._last_time is not None and self._last_watts is not None:
            elapsed = when - self._last_time
            if 0 < elapsed <= self.max_gap:
                average = (self._last_watts + watts) / 2
                self.total_kwh += average * elapsed / 3_600_000
            elif elapsed <= 0:
                # Same or older reading (e.g. a refresh without new data).
                return self.total_kwh
        self._last_time = when
        self._last_watts = watts
        return self.total_kwh

    def reset_baseline(self) -> None:
        """Forget the last reading; the next one starts a new interval."""
        self._last_time = None
        self._last_watts = None
