"""Test the Daikin Madoka config flow."""
from homeassistant import config_entries
from homeassistant.const import CONF_DEVICES
from homeassistant.data_entry_flow import FlowResultType

from custom_components.daikin_madoka.const import DOMAIN

ADDRESS = "68:88:A1:0A:9C:24"


async def test_user_flow_creates_entry(hass):
    """A valid MAC creates a config entry with an upper-cased address list."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICES: "68:88:a1:0a:9c:24"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICES] == [ADDRESS]


async def test_user_flow_rejects_bad_mac(hass):
    """An invalid MAC re-shows the form with an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICES: "not-a-mac"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DEVICES: "not_a_mac"}
