"""Config flow for Reddit Images integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INTERVAL,
    CONF_LIMIT,
    CONF_SELECTION_MODE,
    CONF_SUBREDDIT,
    DEFAULT_INTERVAL,
    DEFAULT_LIMIT,
    DEFAULT_SELECTION_MODE,
    DEFAULT_SUBREDDIT,
    DOMAIN,
    MODE_RANDOM,
    MODE_TOP,
    TOKEN_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

LABEL_INTERVAL = "interval_minutes"
LABEL_SELECTION_MODE = "selection_mode"

SELECTION_MODE_OPTIONS = {
    MODE_RANDOM: "Random from Top",
    MODE_TOP: "Top Post",
}

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_CLIENT_SECRET): cv.string,
    }
)

SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SUBREDDIT, default=DEFAULT_SUBREDDIT): cv.string,
        vol.Required(CONF_LIMIT, default=DEFAULT_LIMIT): vol.All(
            cv.positive_int, vol.Range(min=1, max=100)
        ),
        vol.Required(LABEL_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
            cv.positive_int, vol.Range(min=1)
        ),
        vol.Required(
            LABEL_SELECTION_MODE, default=DEFAULT_SELECTION_MODE
        ): vol.In(SELECTION_MODE_OPTIONS),
    }
)


async def _validate_credentials(
    hass: HomeAssistant, client_id: str, client_secret: str
) -> str | None:
    """Return an error key, or None when the credentials work."""
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(client_id.strip(), client_secret.strip()),
            headers={"User-Agent": USER_AGENT},
        ) as response:
            if response.status == 200:
                payload = await response.json()
                return None if payload.get("access_token") else "invalid_auth"
            if response.status in (401, 403):
                return "invalid_auth"
            _LOGGER.warning("Reddit token endpoint returned %s", response.status)
            return "cannot_connect"
    except Exception as err:
        _LOGGER.warning("Error validating Reddit credentials: %s", err)
        return "cannot_connect"


def _settings_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
    """Map the form fields onto the stored constants."""
    return {
        CONF_SUBREDDIT: user_input[CONF_SUBREDDIT].strip().lower(),
        CONF_LIMIT: user_input[CONF_LIMIT],
        CONF_INTERVAL: user_input[LABEL_INTERVAL],
        CONF_SELECTION_MODE: user_input[LABEL_SELECTION_MODE],
    }


class ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Reddit Images."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._credentials: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Reddit app credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _validate_credentials(
                self.hass,
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
            )
            if error:
                errors["base"] = error
            else:
                self._credentials = {
                    CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                    CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
                }
                return await self.async_step_subreddit()

        return self.async_show_form(
            step_id="user", data_schema=CREDENTIALS_SCHEMA, errors=errors
        )

    async def async_step_subreddit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which subreddit to show."""
        if user_input is not None:
            settings = _settings_from_input(user_input)
            await self.async_set_unique_id(settings[CONF_SUBREDDIT])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=settings[CONF_SUBREDDIT],
                data={**self._credentials, **settings},
            )

        return self.async_show_form(
            step_id="subreddit", data_schema=SETTINGS_SCHEMA
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return OptionsFlowHandler()


class OptionsFlowHandler(OptionsFlow):
    """Handle the integration options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the settings and credentials."""
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            error = await _validate_credentials(
                self.hass,
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
            )
            if error:
                errors["base"] = error
            else:
                options = {
                    CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                    CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
                    **_settings_from_input(user_input),
                }
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_CLIENT_ID, default=current.get(CONF_CLIENT_ID, "")
                ): cv.string,
                vol.Required(
                    CONF_CLIENT_SECRET, default=current.get(CONF_CLIENT_SECRET, "")
                ): cv.string,
                vol.Required(
                    CONF_SUBREDDIT, default=current.get(CONF_SUBREDDIT, DEFAULT_SUBREDDIT)
                ): cv.string,
                vol.Required(
                    CONF_LIMIT, default=current.get(CONF_LIMIT, DEFAULT_LIMIT)
                ): vol.All(cv.positive_int, vol.Range(min=1, max=100)),
                vol.Required(
                    LABEL_INTERVAL, default=current.get(CONF_INTERVAL, DEFAULT_INTERVAL)
                ): vol.All(cv.positive_int, vol.Range(min=1)),
                vol.Required(
                    LABEL_SELECTION_MODE,
                    default=current.get(CONF_SELECTION_MODE, DEFAULT_SELECTION_MODE),
                ): vol.In(SELECTION_MODE_OPTIONS),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
