# CLAUDE.md — ha-daikin-madoka

Home Assistant integration for the Daikin BRC1H ("Madoka") BLE thermostat.
Integration domain: `daikin_madoka`. HA-only (no CLI).

## Always update the changelog

For any user-facing change, add an entry under `## [Unreleased]` in
`CHANGELOG.md` (Keep a Changelog format: Added / Changed / Fixed / Removed).
On release, move it under a new version heading and bump the version in **both**
`manifest.json` and `pyproject.toml` (keep them in sync), then tag `vX.Y.Z`.

## The one rule that must not regress

**Never run our own `BleakScanner` or shell out to `bluetoothctl`.** That is the
bug this project exists to fix: a private scanner collided with Home Assistant's
scanner on the same adapter, BlueZ returned `org.bluez.Error.InProgress`, and the
BLE session wedged until HA restarted.

Instead:
- Get the device from HA: `bluetooth.async_ble_device_from_address(hass, addr,
  connectable=True)`; raise `ConfigEntryNotReady` if it returns `None`.
- Connect via `bleak_retry_connector.establish_connection` (never raw
  `BleakClient.connect()` — HA warns and bypasses connection-slot management).
- `tests/test_vendored.py` enforces this; keep it green.

## Architecture

- `custom_components/daikin_madoka/madoka/` — the vendored BLE protocol library
  (derived from pymadoka, MIT © Manuel Durán). It is **ours to maintain** now,
  but keep Durán's copyright in `LICENSE`. Keep it lint-clean (no exemptions).
- `coordinator.py` — one `DataUpdateCoordinator` per device polls over the active
  connection; climate + sensor entities are `CoordinatorEntity` and share it.
- The config entry uses the legacy shape (`CONF_DEVICES` list, fixed
  `unique_id = "BRC1H-id"`). **Don't change the domain or that shape** — it would
  break existing installs' entities/history.

## Dev workflow (uv)

```bash
uv sync                                        # needs a C compiler for some HA deps
uv run ruff format --check custom_components tests
uv run ruff check custom_components tests
uv run pytest -q
```

- ruff: line length is owned by `ruff format`; `E501` is ignored on purpose.
- Tests that trigger HA's bluetooth setup must request the `enable_bluetooth`
  fixture (mocks the scanner + management socket; otherwise pytest-socket blocks
  the real HCI socket).
- `pytest-homeassistant-custom-component` installs HA core but not per-integration
  requirements; the bluetooth/usb component deps are listed in the `dev`
  dependency group so the import chain resolves.

## Deployment

Runs on the NixOS host **banana** via the flake at `/etc/nixos`. The component is
pinned by `rev` + `hash` in `hosts/banana/pkgs/daikin_madoka/default.nix`. After
pushing here, bump that rev/hash, then `nixos-rebuild test` (never `switch`
first) → verify the climate entity polls cleanly and turn-off works → `switch`.
