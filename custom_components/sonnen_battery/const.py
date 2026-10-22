"""Constants for the Sonnen Battery integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sonnen_battery"
MANUFACTURER: Final = "sonnen"

DEFAULT_SCAN_INTERVAL: Final = 10  # seconds; short keeps the kWh counters accurate
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 300

# Settings in /api/v2/configurations
CONF_KEY_SERIAL: Final = "DE_Ticket_Number"
CONF_KEY_OPERATING_MODE: Final = "EM_OperatingMode"
CONF_KEY_BACKUP_RESERVE: Final = "EM_USOC"

# Operating modes the select offers: option -> value the battery uses.
OPERATING_MODES: Final = {
    "manual": "1",
    "automatic": "2",
    "time_of_use": "10",
    "optimisation": "11",
}
