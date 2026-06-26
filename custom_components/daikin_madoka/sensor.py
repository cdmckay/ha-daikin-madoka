"""Support for Daikin Madoka temperature sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MadokaDataUpdateCoordinator
from .madoka import ConnectionStatus


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Daikin Madoka sensors based on a config entry."""
    entities = []
    for coordinator in entry.runtime_data.values():
        entities.append(MadokaIndoorSensor(coordinator))
        entities.append(MadokaOutdoorSensor(coordinator))
    async_add_entities(entities)


class MadokaSensor(CoordinatorEntity[MadokaDataUpdateCoordinator], SensorEntity):
    """Base representation of a Madoka temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(
        self, coordinator: MadokaDataUpdateCoordinator, suffix: str, name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.controller = coordinator.controller
        self._suffix = suffix
        self._name = name

    @property
    def available(self) -> bool:
        """Return the availability."""
        return (
            super().available
            and self.controller.connection.connection_status
            is ConnectionStatus.CONNECTED
        )

    @property
    def unique_id(self):
        """Return a unique ID."""
        return f"{self.controller.connection.address}_{self._suffix}"

    @property
    def name(self):
        """Return the name of the sensor."""
        base_name = (
            self.controller.connection.name
            if self.controller.connection.name is not None
            else self.controller.connection.address
        )
        return f"{base_name} {self._name}"

    @property
    def device_info(self):
        """Return device registry information shared with the climate entity."""
        return {
            "identifiers": {(DOMAIN, self.controller.connection.address)},
            "name": (
                self.controller.connection.name
                if self.controller.connection.name is not None
                else self.controller.connection.address
            ),
            "manufacturer": "DAIKIN",
            "model": "BRC1H",
        }


class MadokaIndoorSensor(MadokaSensor):
    """Indoor temperature sensor."""

    def __init__(self, coordinator: MadokaDataUpdateCoordinator) -> None:
        """Initialize the indoor sensor."""
        super().__init__(coordinator, "indoor_temperature", "Indoor Temperature")

    @property
    def native_value(self):
        """Return the indoor temperature."""
        if self.controller.temperatures.status is None:
            return None
        return self.controller.temperatures.status.indoor


class MadokaOutdoorSensor(MadokaSensor):
    """Outdoor temperature sensor."""

    def __init__(self, coordinator: MadokaDataUpdateCoordinator) -> None:
        """Initialize the outdoor sensor."""
        super().__init__(coordinator, "outdoor_temperature", "Outdoor Temperature")

    @property
    def native_value(self):
        """Return the outdoor temperature."""
        if self.controller.temperatures.status is None:
            return None
        return self.controller.temperatures.status.outdoor
