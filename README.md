# Daikin Madoka (BRC1H) — Home Assistant integration

Control a Daikin air conditioner through a **BRC1H "Madoka"** Bluetooth Low
Energy thermostat from Home Assistant.

This is a single, self-contained custom integration: the BLE protocol library
(`pymadoka`) is **vendored** under `custom_components/daikin_madoka/madoka/`, so
there is no separate PyPI dependency to keep in lockstep.

## Why this fork exists

Earlier versions ran their **own `BleakScanner`** on the Bluetooth adapter and
force-disconnected the device with `bluetoothctl` before every connect. On a
host where Home Assistant's `bluetooth` integration already owns the adapter,
those two scanners collided and BlueZ rejected the connect with
`org.bluez.Error.InProgress`, leaving a wedged session — the thermostat would
stop responding to commands (e.g. "turn off") until Home Assistant was
restarted.

This version follows Home Assistant's Bluetooth best practices:

- The device is obtained from HA's central scanner via
  `bluetooth.async_ble_device_from_address(..., connectable=True)` — the
  integration never starts its own scanner.
- Connections are made through `bleak-retry-connector.establish_connection`,
  which reserves a connection slot and serialises attempts.
- A single `DataUpdateCoordinator` per device polls over the active connection,
  so the climate and sensor entities share one update cycle.
- The manifest declares `dependencies: ["bluetooth_adapters"]`.

## Installation (HACS)

Add this repository as a custom repository (category: *Integration*), install
**Daikin Madoka**, restart Home Assistant, then add the integration and enter
the BRC1H's Bluetooth MAC address. Pair the device with the host first
(`bluetoothctl pair <MAC>`).

## Development

This repo uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync                                   # create the dev env
uv run ruff format --check custom_components
uv run ruff check custom_components
uv run pytest -q
```

`tests/test_vendored.py` is a hardware-free regression guard that fails if the
self-scanning code ever returns.
