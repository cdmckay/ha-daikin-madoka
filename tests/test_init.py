"""Test setup/teardown of the Daikin Madoka integration."""
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICES
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_madoka.const import DOMAIN, UNIQUE_ID
from custom_components.daikin_madoka.madoka import ConnectionStatus

ADDRESS = "68:88:A1:0A:9C:24"


def _make_controller():
    """Build a stand-in controller that reports a healthy connection."""
    controller = MagicMock()
    controller.connection.address = ADDRESS
    controller.connection.name = "BRC1H"
    controller.connection.connection_status = ConnectionStatus.CONNECTED
    controller.info = {}
    controller.start = AsyncMock()
    controller.stop = AsyncMock()
    controller.update = AsyncMock()
    controller.read_info = AsyncMock(return_value={})
    for feature in (
        "temperatures",
        "set_point",
        "operation_mode",
        "power_state",
        "fan_speed",
    ):
        getattr(controller, feature).status = None
    return controller


async def test_setup_entry_uses_ha_scanner(hass, enable_bluetooth):
    """Setup resolves the device via HA's scanner and loads the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=UNIQUE_ID, data={CONF_DEVICES: [ADDRESS]}
    )
    entry.add_to_hass(hass)

    controller = _make_controller()
    with patch(
        "custom_components.daikin_madoka.bluetooth.async_ble_device_from_address",
        return_value=MagicMock(name="BLEDevice"),
    ) as mock_get_device, patch(
        "custom_components.daikin_madoka.Controller", return_value=controller
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert mock_get_device.called
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_retries_when_device_not_seen(hass, enable_bluetooth):
    """If HA has not seen the device advertise, setup is retried (not failed)."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=UNIQUE_ID, data={CONF_DEVICES: [ADDRESS]}
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.daikin_madoka.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
