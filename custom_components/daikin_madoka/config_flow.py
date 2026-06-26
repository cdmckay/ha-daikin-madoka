"""Config flow for the Daikin Madoka integration."""

from __future__ import annotations

import re

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_DEVICES

from .const import DOMAIN, TITLE, UNIQUE_ID

MAC_RE = re.compile(r"[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\1[0-9a-f]{2}){4}$")


class DaikinMadokaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Daikin Madoka."""

    VERSION = 1

    @property
    def _schema(self) -> vol.Schema:
        return vol.Schema({vol.Required(CONF_DEVICES, default=""): cv.string})

    @staticmethod
    def _validate_macs(macs: list[str]) -> bool:
        return bool(macs) and all(MAC_RE.match(mac.lower()) for mac in macs)

    async def async_step_user(self, user_input=None):
        """Handle a user-initiated config flow."""
        errors: dict[str, str] = {}

        await self.async_set_unique_id(UNIQUE_ID)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            macs = [
                mac.strip()
                for mac in user_input[CONF_DEVICES].split(",")
                if mac.strip()
            ]
            if not self._validate_macs(macs):
                errors[CONF_DEVICES] = "not_a_mac"

            if not errors:
                return self.async_create_entry(
                    title=TITLE,
                    data={CONF_DEVICES: [mac.upper() for mac in macs]},
                )

        return self.async_show_form(
            step_id="user", data_schema=self._schema, errors=errors
        )
