"""Regression guards on the vendored pymadoka library.

The integration must NEVER revert to running its own BLE scanner: doing so
collided with Home Assistant's central scanner on the same adapter and wedged
the link with org.bluez `InProgress` errors (the original bug). These checks
need no Home Assistant runtime and no hardware.
"""

import inspect
from pathlib import Path

from custom_components.daikin_madoka.madoka import Connection, Controller, connection


def test_connection_accepts_injected_ble_device():
    """Connection must take a device + provider from Home Assistant."""
    params = inspect.signature(Connection.__init__).parameters
    assert "ble_device" in params
    assert "ble_device_provider" in params


def test_controller_forwards_ble_device():
    """Controller must forward the injected device through to Connection."""
    params = inspect.signature(Controller.__init__).parameters
    assert "ble_device" in params
    assert "ble_device_provider" in params


def test_library_never_scans_or_force_disconnects():
    """The self-scan / force-disconnect machinery must stay gone for good."""
    assert not hasattr(connection, "discover_devices")
    assert not hasattr(connection, "force_device_disconnect")
    assert not hasattr(Connection, "_select_device")

    source = Path(connection.__file__).read_text()
    # A scanner must never be imported or instantiated (comments may still
    # mention it to explain why it was removed).
    import_lines = [
        line
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert not any("BleakScanner" in line for line in import_lines)
    assert "BleakScanner(" not in source
    assert "bluetoothctl" not in source
