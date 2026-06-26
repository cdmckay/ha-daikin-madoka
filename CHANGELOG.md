# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.0] - 2026-06-26

Single, self-contained integration with the BLE library vendored in.

### Changed
- **Merged the `daikin_madoka` integration and the `pymadoka` library into one
  repo**, with `pymadoka` vendored under `custom_components/daikin_madoka/madoka/`.
  There is no longer a separate library dependency.
- **Rewrote BLE handling to follow Home Assistant's Bluetooth best practices:**
  the device is obtained from HA's central scanner via
  `bluetooth.async_ble_device_from_address(..., connectable=True)` and connected
  with `bleak_retry_connector.establish_connection`. The integration no longer
  runs its own `BleakScanner`.
- Polling now goes through a single `DataUpdateCoordinator` per device, shared by
  the climate and sensor entities.
- Manifest declares `dependencies: ["bluetooth_adapters"]`,
  `integration_type: "device"`, and `iot_class: "local_polling"`.

### Fixed
- The thermostat could become unresponsive to commands (e.g. "turn off") until
  Home Assistant was restarted. The library's own scanner collided with HA's
  scanner on the same adapter, and BlueZ rejected the connect with
  `org.bluez.Error.InProgress`, leaving a wedged session.

### Removed
- The self-scanning / `bluetoothctl` force-disconnect code path.
- The unused clean-filter feature (planned to return as proper entities — see
  the README roadmap).
- The standalone CLI and MQTT modules from the vendored library (HA-only).

[Unreleased]: https://github.com/cdmckay/ha-daikin-madoka/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/cdmckay/ha-daikin-madoka/releases/tag/v3.0.0
