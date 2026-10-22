# Sonnen Battery (Local API) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![CI](https://github.com/zafayar/ha-sonnen-battery/actions/workflows/ci.yml/badge.svg)](https://github.com/zafayar/ha-sonnen-battery/actions/workflows/ci.yml)

A Home Assistant integration for Sonnen home batteries. It talks to the battery directly over your local network using sonnen's JSON API (v2), with no cloud account.

**Works with the Energy dashboard out of the box.** The battery only reports live power (watts), but the Energy dashboard needs running energy totals (kWh). This integration turns the live readings into six kWh counters with the right device class, state class and unit, so you can pick them straight away: no Riemann sum helpers, no template sensors.

## Features

- Energy dashboard ready: grid import and export, battery charge and discharge, solar production and house consumption in kWh
- Live power for every flow, with both signed and split (import/export, charge/discharge) sensors
- State of charge, remaining energy, system status, grid frequency, cycle count, state of health and full charge capacity
- Problem alerts from the battery's status light and fault flags, plus the time of the last full charge
- Change the operating mode and backup reserve (needs write access)
- `sonnen_battery.set_power` action to charge or discharge at a fixed power from automations (manual mode)
- Set up from the UI, with re-authentication, reconfiguration and a polling interval option
- Diagnostics download with the token and serial number removed
- No extra Python packages

## Requirements

- A Sonnen Battery with the JSON API v2 and an API token (most systems from software 1.8 onwards). Older systems that only offer the legacy APIs on ports 8080 or 7979 aren't supported.
- Home Assistant 2025.2 or later

### Get an API token

1. Open the battery's dashboard in a browser: `http://<battery IP>/`
2. Log in as the **User**.
3. Go to **Software-Integration**.
4. Turn on **JSON API (Read API)**. Turn on **Write API** too if you want to change the operating mode or backup reserve from Home Assistant.
5. Copy the **API token**.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=zafayar&repository=ha-sonnen-battery&category=integration)

Or by hand:

1. In HACS, open the menu (⋮) and choose **Custom repositories**.
2. Add `https://github.com/zafayar/ha-sonnen-battery` with the category **Integration**.
3. Find **Sonnen Battery (Local API)** in HACS and download it.
4. Restart Home Assistant.

### Manual

Copy `custom_components/sonnen_battery` into your Home Assistant `config/custom_components/` folder and restart.

## Setup

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=sonnen_battery)

**Settings → Devices & services → Add integration → Sonnen Battery (Local API)**, then enter the battery's IP address and the API token.

To change how often it polls, open the integration and choose **Configure**. The default is 10 seconds. Shorter intervals make the energy counters more accurate.

## Energy dashboard

Go to **Settings → Dashboards → Energy** and choose:

| Energy dashboard setting     | Sensor                                       |
| ---------------------------- | -------------------------------------------- |
| Grid consumption             | `sensor.sonnen_battery_grid_import_energy`   |
| Return to grid               | `sensor.sonnen_battery_grid_export_energy`   |
| Solar production             | `sensor.sonnen_battery_solar_production_energy` |
| Battery: energy going in     | `sensor.sonnen_battery_battery_charge_energy` |
| Battery: energy coming out   | `sensor.sonnen_battery_battery_discharge_energy` |

`sensor.sonnen_battery_house_consumption_energy` is there if you want to track the house's total as an individual device.

For the dashboard's live power view, use `sensor.sonnen_battery_grid_power` (positive when importing) and `sensor.sonnen_battery_battery_power` (positive when discharging). These follow Home Assistant's sign conventions.

### How the counters work

Every poll, the integration reads the live power for each direction and adds up the energy since the previous reading (trapezoidal rule). The totals:

- are `device_class: energy`, `state_class: total_increasing`, in kWh
- are saved and restored across Home Assistant restarts, so they never go backwards
- don't count anything across gaps longer than 5 minutes (for example while the battery or Home Assistant is offline) rather than guess what happened

If your battery's own meters have lifetime counters, they are also available as **Meter … energy imported/exported** diagnostic sensors. They are disabled by default because what each counter measures depends on how the meters were installed. Check them against your inverter or electricity bill before using them in the Energy dashboard.

## Entities

| Entity | Notes |
| --- | --- |
| House consumption / Solar production power | W |
| Grid power | W, positive = import, negative = export |
| Grid import power / Grid export power | W, always ≥ 0 |
| Battery power | W, positive = discharging, negative = charging |
| Battery charge power / Battery discharge power | W, always ≥ 0 |
| Six `… energy` sensors | kWh, for the Energy dashboard |
| State of charge | % usable charge (USOC) |
| State of charge (real) | % raw charge (RSOC), disabled by default |
| Remaining energy | if your firmware reports it |
| System status | e.g. `OnGrid`, `OffGrid` |
| Charging / Discharging / On grid | binary sensors |
| Problem | binary sensor: on when the status light is red or the battery reports a fault (BMS alarm, hardware shutdown, inverter over-temperature, electrolyte leakage) |
| Discharge not allowed | binary sensor: sonnen's battery care is blocking discharge, diagnostic |
| Status light | the light ring on the battery: pulsing white, green or orange, solid or blinking red, or off |
| Last full charge | timestamp |
| Shutdown reason | why the battery's DC side shut down, or `none`; disabled by default |
| Full charge capacity | the battery's measured capacity, diagnostic |
| Operating mode | select: Manual, Self-consumption, Time of use, Optimisation |
| Backup reserve | number, % kept back for power cuts |
| Grid frequency, AC voltage, battery voltage, cycle count, state of health | diagnostic |

## Actions

### `sonnen_battery.set_power`

Charges or discharges the battery at a fixed power. The battery only accepts this in **Manual** operating mode, and the token needs write access. Send 0 W to stop.

```yaml
action: sonnen_battery.set_power
data:
  config_entry_id: <your battery>   # pick it in the UI action editor
  direction: charge                  # or discharge
  power: 2000                        # watts
```

A typical use is charging from the grid during a cheap tariff window: set the operating mode to Manual, call `set_power`, then switch back to Self-consumption afterwards.

## Troubleshooting

- **Problem is on**: check the **Status light** and **Shutdown reason** sensors, then the battery's own dashboard. Contact your installer or sonnen for red-light faults.

- **"The battery rejected the API token"**: check the token in **Software-Integration** and that the JSON API is turned on. If you generate a new token later, Home Assistant asks for it automatically.
- **Operating mode or backup reserve missing**: the token can't read the battery's settings. Turn on the Read API.
- **"The battery didn't accept the change"**: turn on the Write API.
- **Logs**: add this to `configuration.yaml`:

  ```yaml
  logger:
    logs:
      custom_components.sonnen_battery: debug
  ```

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest --cov
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Tests use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component), which needs the same Python version as current Home Assistant (3.14).

## Credits

Inspired by [weltmeyer/ha_sonnenbatterie](https://github.com/weltmeyer/ha_sonnenbatterie) and [mrpointblue/sonnenBatterie-Integration](https://github.com/mrpointblue/sonnenBatterie-Integration). This is an independent project, not affiliated with or endorsed by sonnen GmbH.

## Licence

MIT
