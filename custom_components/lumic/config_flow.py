from homeassistant import config_entries
from .const import DOMAIN
import voluptuous as vol
import logging

_LOGGER = logging.getLogger(__name__)

class LumicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Example config flow."""

    data = None

    async def async_step_user(self, info):
        """Config flow step user."""
        if info is not None:
            if not info.get("client_id") is None and not info.get("client_secret") is None and not info.get("home_id") is None:
                self.data = info
                return await self.async_step_finish()

        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({
                vol.Required("home_id"): int,
                vol.Required("client_id"): str,
                vol.Required("client_secret"): str,
            })
        )
    
    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title="Lumic Lighting", data=self.data)
