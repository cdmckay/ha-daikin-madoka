"""The Daikin Madoka (BRC1H) integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICES, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONNECT_TIMEOUT
from .coordinator import MadokaDataUpdateCoordinator
from .madoka import ConnectionStatus, Controller

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]

type MadokaConfigEntry = ConfigEntry[dict[str, MadokaDataUpdateCoordinator]]


def _make_ble_device_provider(hass: HomeAssistant, address: str):
    """Return a zero-arg callable yielding the freshest BLEDevice for address."""

    def _provider():
        return bluetooth.async_ble_device_from_address(hass, address, connectable=True)

    return _provider


async def _safe_stop(controller: Controller) -> None:
    """Stop a controller's connection loop, swallowing errors."""
    try:
        await asyncio.wait_for(controller.stop(), timeout=10)
    except Exception:  # noqa: BLE001
        pass


async def async_setup_entry(hass: HomeAssistant, entry: MadokaConfigEntry) -> bool:
    """Set up Daikin Madoka from a config entry."""
    coordinators: dict[str, MadokaDataUpdateCoordinator] = {}
    started: list[Controller] = []

    try:
        for raw_address in entry.data[CONF_DEVICES]:
            address = raw_address.upper()

            # Obtain the device from HA's central scanner — never run our own.
            ble_device = bluetooth.async_ble_device_from_address(
                hass, address, connectable=True
            )
            if ble_device is None:
                raise ConfigEntryNotReady(
                    f"{address} not seen yet by any Bluetooth adapter"
                )

            controller = Controller(
                address,
                ble_device=ble_device,
                ble_device_provider=_make_ble_device_provider(hass, address),
            )

            # pymadoka's start() runs a (re)connect loop; bound it so an
            # unreachable thermostat can't hang HA's setup. wait_for can cancel
            # it because the library propagates CancelledError.
            try:
                await asyncio.wait_for(controller.start(), timeout=CONNECT_TIMEOUT)
            except (asyncio.TimeoutError, asyncio.CancelledError) as err:
                await _safe_stop(controller)
                raise ConfigEntryNotReady(f"Timed out connecting to {address}") from err

            if (
                controller.connection.connection_status
                is not ConnectionStatus.CONNECTED
            ):
                await _safe_stop(controller)
                raise ConfigEntryNotReady(f"Could not connect to {address}")

            started.append(controller)
            coordinator = MadokaDataUpdateCoordinator(hass, entry, controller)
            await coordinator.async_config_entry_first_refresh()
            coordinators[address] = coordinator
    except Exception:
        # Don't leak half-started connection loops if any device failed.
        for controller in started:
            await _safe_stop(controller)
        raise

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MadokaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        for coordinator in entry.runtime_data.values():
            await _safe_stop(coordinator.controller)
    return unload_ok
