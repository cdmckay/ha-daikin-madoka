"""Support for the Daikin Madoka HVAC."""

from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_TEMP, MIN_TEMP
from .coordinator import MadokaDataUpdateCoordinator
from .madoka import (
    ConnectionException,
    ConnectionStatus,
    FanSpeedEnum,
    FanSpeedStatus,
    OperationModeEnum,
    OperationModeStatus,
    PowerStateStatus,
    SetPointStatus,
)

_LOGGER = logging.getLogger(__name__)

HA_MODE_TO_DAIKIN = {
    HVACMode.FAN_ONLY: OperationModeEnum.FAN,
    HVACMode.DRY: OperationModeEnum.DRY,
    HVACMode.COOL: OperationModeEnum.COOL,
    HVACMode.HEAT: OperationModeEnum.HEAT,
    HVACMode.AUTO: OperationModeEnum.AUTO,
    HVACMode.OFF: OperationModeEnum.AUTO,
}

DAIKIN_TO_HA_MODE = {
    OperationModeEnum.FAN: HVACMode.FAN_ONLY,
    OperationModeEnum.DRY: HVACMode.DRY,
    OperationModeEnum.COOL: HVACMode.COOL,
    OperationModeEnum.HEAT: HVACMode.HEAT,
    OperationModeEnum.AUTO: HVACMode.AUTO,
}

HA_FAN_MODE_TO_DAIKIN = {
    FAN_LOW: FanSpeedEnum.LOW,
    FAN_MEDIUM: FanSpeedEnum.MID,
    FAN_HIGH: FanSpeedEnum.HIGH,
    FAN_AUTO: FanSpeedEnum.AUTO,
}

DAIKIN_TO_HA_FAN_MODE = {
    FanSpeedEnum.LOW: FAN_LOW,
    FanSpeedEnum.MID: FAN_MEDIUM,
    FanSpeedEnum.HIGH: FAN_HIGH,
    FanSpeedEnum.AUTO: FAN_AUTO,
}

DAIKIN_TO_HA_CURRENT_HVAC_MODE = {
    OperationModeEnum.FAN: HVACAction.FAN,
    OperationModeEnum.DRY: HVACAction.DRYING,
    OperationModeEnum.COOL: HVACAction.COOLING,
    OperationModeEnum.HEAT: HVACAction.HEATING,
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Daikin Madoka climate entities based on a config entry."""
    async_add_entities(
        DaikinMadokaClimate(coordinator) for coordinator in entry.runtime_data.values()
    )


class DaikinMadokaClimate(
    CoordinatorEntity[MadokaDataUpdateCoordinator], ClimateEntity
):
    """Representation of a Daikin Madoka HVAC."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP

    def __init__(self, coordinator: MadokaDataUpdateCoordinator) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)
        self.controller = coordinator.controller

    @property
    def available(self) -> bool:
        """Return the availability."""
        return (
            super().available
            and self.controller.connection.connection_status
            is ConnectionStatus.CONNECTED
        )

    @property
    def name(self):
        """Return the name of the thermostat, if any."""
        return (
            self.controller.connection.name
            if self.controller.connection.name is not None
            else self.controller.connection.address
        )

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self.controller.connection.address

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self.controller.temperatures.status is None:
            return None
        return self.controller.temperatures.status.indoor

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.controller.set_point.status is None:
            return None

        if self.hvac_mode == HVACMode.HEAT:
            return self.controller.set_point.status.heating_set_point
        return self.controller.set_point.status.cooling_set_point

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        try:
            if self.controller.set_point.status is None:
                return
            if self.controller.operation_mode.status is None:
                return

            target_temperature = kwargs.get(ATTR_TEMPERATURE)
            if target_temperature is None:
                return

            new_cooling_set_point = self.controller.set_point.status.cooling_set_point
            new_heating_set_point = self.controller.set_point.status.heating_set_point
            if (
                self.controller.operation_mode.status.operation_mode
                != OperationModeEnum.HEAT
            ):
                new_cooling_set_point = round(target_temperature)
            if (
                self.controller.operation_mode.status.operation_mode
                != OperationModeEnum.COOL
            ):
                new_heating_set_point = round(target_temperature)

            await self.controller.set_point.update(
                SetPointStatus(new_cooling_set_point, new_heating_set_point)
            )
            await self.coordinator.async_request_refresh()
        except ConnectionAbortedError:
            _LOGGER.warning(
                "Could not set target temperature on %s. Connection not available.",
                self.name,
            )
        except ConnectionException:
            pass

    @property
    def hvac_mode(self):
        """Return current operation ie. heat, cool, idle."""
        if self.controller.power_state.status is None:
            return None
        if self.controller.operation_mode.status is None:
            return None

        if self.controller.power_state.status.turn_on is False:
            return HVACMode.OFF

        return DAIKIN_TO_HA_MODE.get(
            self.controller.operation_mode.status.operation_mode
        )

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return list(HA_MODE_TO_DAIKIN)

    @property
    def hvac_action(self):
        """Return the HVAC current action."""
        if self.controller.power_state.status is None:
            return None
        if self.controller.operation_mode.status is None:
            return None

        if self.controller.power_state.status.turn_on is False:
            return HVACAction.OFF

        if (
            self.controller.operation_mode.status.operation_mode
            == OperationModeEnum.AUTO
        ):
            if self.target_temperature is None or self.current_temperature is None:
                return None
            if self.target_temperature >= self.current_temperature:
                return HVACAction.HEATING
            return HVACAction.COOLING

        return DAIKIN_TO_HA_CURRENT_HVAC_MODE.get(
            self.controller.operation_mode.status.operation_mode
        )

    async def async_set_hvac_mode(self, hvac_mode):
        """Set HVAC mode."""
        try:
            if hvac_mode != HVACMode.OFF:
                await self.controller.operation_mode.update(
                    OperationModeStatus(HA_MODE_TO_DAIKIN.get(hvac_mode))
                )
            await self.controller.power_state.update(
                PowerStateStatus(hvac_mode != HVACMode.OFF)
            )
            await self.coordinator.async_request_refresh()
        except ConnectionAbortedError:
            _LOGGER.warning(
                "Could not set HVAC mode on %s. Connection not available.", self.name
            )
        except ConnectionException:
            pass

    @property
    def fan_mode(self):
        """Return the fan setting."""
        if self.controller.fan_speed.status is None:
            return None
        if self.hvac_mode == HVACMode.HEAT:
            return DAIKIN_TO_HA_FAN_MODE.get(
                self.controller.fan_speed.status.heating_fan_speed
            )
        return DAIKIN_TO_HA_FAN_MODE.get(
            self.controller.fan_speed.status.cooling_fan_speed
        )

    async def async_set_fan_mode(self, fan_mode):
        """Set fan mode."""
        try:
            await self.controller.fan_speed.update(
                FanSpeedStatus(
                    HA_FAN_MODE_TO_DAIKIN.get(fan_mode),
                    HA_FAN_MODE_TO_DAIKIN.get(fan_mode),
                )
            )
            await self.coordinator.async_request_refresh()
        except ConnectionAbortedError:
            _LOGGER.warning(
                "Could not set fan mode on %s. Connection not available.", self.name
            )
        except ConnectionException:
            pass

    @property
    def fan_modes(self):
        """List of available fan modes."""
        return list(HA_FAN_MODE_TO_DAIKIN)

    async def async_turn_on(self):
        """Turn device on."""
        try:
            await self.controller.power_state.update(PowerStateStatus(True))
            await self.coordinator.async_request_refresh()
        except ConnectionAbortedError:
            _LOGGER.warning(
                "Could not turn on %s. Connection not available.", self.name
            )
        except ConnectionException:
            pass

    async def async_turn_off(self):
        """Turn device off."""
        try:
            await self.controller.power_state.update(PowerStateStatus(False))
            await self.coordinator.async_request_refresh()
        except ConnectionAbortedError:
            _LOGGER.warning(
                "Could not turn off %s. Connection not available.", self.name
            )
        except ConnectionException:
            pass

    @property
    def device_info(self):
        """Return a device description for the device registry."""
        info = self.controller.info or {}
        model = (
            "BRC1H" + info["Model Number String"]
            if "Model Number String" in info
            else "BRC1H"
        )
        sw_version = info.get("Software Revision String", "")
        return {
            "identifiers": {(DOMAIN, self.unique_id)},
            "name": self.name,
            "manufacturer": "DAIKIN",
            "model": model,
            "sw_version": sw_version,
        }
