"""DataUpdateCoordinator for the Daikin Madoka integration.

A single coordinator per BRC1H serialises all polling over the active BLE
connection, so the climate and sensor entities share one update cycle instead
of each opening their own conversation with the device (which used to multiply
BLE traffic and contention).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL
from .madoka import ConnectionException, ConnectionStatus, Controller

_LOGGER = logging.getLogger(__name__)


class MadokaDataUpdateCoordinator(DataUpdateCoordinator[Controller]):
    """Polls a single Madoka controller over its active BLE connection."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, controller: Controller
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {controller.connection.address}",
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.controller = controller

    @property
    def address(self) -> str:
        """Return the BRC1H MAC address."""
        return self.controller.connection.address

    async def _async_update_data(self) -> Controller:
        """Fetch the latest state from the device.

        Re-establishing a dropped connection is handled in the background by the
        library's disconnect callback; here we only poll when connected and
        report the controller (whose feature ``.status`` objects the entities
        read directly).
        """
        if (
            self.controller.connection.connection_status
            is not ConnectionStatus.CONNECTED
        ):
            raise UpdateFailed(f"{self.address} is not connected")

        try:
            if not self.controller.info:
                await self.controller.read_info()
            await self.controller.update()
        except (ConnectionAbortedError, ConnectionException) as err:
            raise UpdateFailed(f"Error communicating with {self.address}: {err}") from err

        return self.controller
