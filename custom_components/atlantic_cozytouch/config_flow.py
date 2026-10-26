"""UI-only Atlantic account configuration; validation only reads the pump."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import AtlanticAuthError, AtlanticError, AtlanticReadOnlyClient
from .const import DOMAIN, OPT_EXPERIMENTAL_CROSS_DEVICE_COP, OPT_API_DISCOVERY


class AtlanticReadOnlyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure vendor cloud monitoring without any write capability."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Expose a clearly labelled user opt-in for experimental COP."""
        return AtlanticReadOnlyOptionsFlow()


    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = AtlanticReadOnlyClient(
                async_get_clientsession(self.hass),
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.async_read()
            except AtlanticAuthError:
                errors["base"] = "invalid_auth"
            except AtlanticError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_USERNAME].strip().lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Atlantic CozyTouch",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )


class AtlanticReadOnlyOptionsFlow(config_entries.OptionsFlow):
    """Opt-in to an experimental 1:1 cross-module hydraulic estimate.

    The cloud may expose the same physical heat pump as multiple logical
    devices. This option enables joining exactly one interface and one
    generator; it cannot prove their actual hydraulic relationship.
    """

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    OPT_EXPERIMENTAL_CROSS_DEVICE_COP: (
                        user_input.get(OPT_EXPERIMENTAL_CROSS_DEVICE_COP) is True
                    ),
                    OPT_API_DISCOVERY: user_input.get(OPT_API_DISCOVERY) is True,
                },
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    OPT_EXPERIMENTAL_CROSS_DEVICE_COP,
                    default=self.config_entry.options.get(
                        OPT_EXPERIMENTAL_CROSS_DEVICE_COP, False
                    ),
                ): bool,
                vol.Optional(
                    OPT_API_DISCOVERY,
                    default=self.config_entry.options.get(OPT_API_DISCOVERY, False),
                ): bool,
            }),
        )
