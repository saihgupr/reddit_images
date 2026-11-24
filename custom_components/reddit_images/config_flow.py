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
    CONF_SOURCE,
    CONF_SUBREDDIT,
    DEFAULT_INTERVAL,
    DEFAULT_LIMIT,
    DEFAULT_SELECTION_MODE,
    DEFAULT_SOURCE,
    DEFAULT_SUBREDDIT,
    DOMAIN,
    MODE_RANDOM,
    MODE_TOP,
    SOURCE_ARCHIVE,
    SOURCE_AUTO,
    SOURCE_REDDIT,
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

SOURCE_OPTIONS = {
    SOURCE_AUTO: "Automatic (Reddit app if it works, otherwise the archive)",
    SOURCE_ARCHIVE: "Archive only (no Reddit app needed)",
    SOURCE_REDDIT: "Reddit API only (approved app required)",
}

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SOURCE, default=DEFAULT_SOURCE): vol.In(SOURCE_OPTIONS),
        vol.Optional(CONF_CLIENT_ID, default=""): cv.string,
        vol.Optional(CONF_CLIENT_SECRET, default=""): cv.string,
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


async def _async_check_source(
    hass: HomeAssistant, source: str, client_id: str, client_secret: str
) -> str | None:
    """Return an error key, or None when the chosen source can be used."""
    if source == SOURCE_ARCHIVE:
        return None

    if not client_id or not client_secret:
        return "credentials_required" if source == SOURCE_REDDIT else None

    error = await _validate_credentials(hass, client_id, client_secret)
    if error and source == SOURCE_AUTO:
        _LOGGER.warning(
            "Reddit rejected the app credentials (%s). Reddit Images keeps working "
            "and reads from the Arctic Shift archive instead",
            error,
        )
        return None
    return error


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
        """Ask for the data source and optional Reddit app credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            source = user_input[CONF_SOURCE]
            client_id = (user_input.get(CONF_CLIENT_ID) or "").strip()
            client_secret = (user_input.get(CONF_CLIENT_SECRET) or "").strip()
            error = await _async_check_source(
                self.hass, source, client_id, client_secret
            )
            if error:
                errors["base"] = error
            else:
                self._credentials = {
                    CONF_SOURCE: source,
                    CONF_CLIENT_ID: client_id,
                    CONF_CLIENT_SECRET: client_secret,
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
        """Edit the settings, data source and credentials."""
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            source = user_input[CONF_SOURCE]
            client_id = (user_input.get(CONF_CLIENT_ID) or "").strip()
            client_secret = (user_input.get(CONF_CLIENT_SECRET) or "").strip()
            error = await _async_check_source(
                self.hass, source, client_id, client_secret
            )
            if error:
                errors["base"] = error
            else:
                options = {
                    CONF_SOURCE: source,
                    CONF_CLIENT_ID: client_id,
                    CONF_CLIENT_SECRET: client_secret,
                    **_settings_from_input(user_input),
                }
                return self.async_create_entry(title="", data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SOURCE, default=current.get(CONF_SOURCE, DEFAULT_SOURCE)
                ): vol.In(SOURCE_OPTIONS),
                vol.Optional(
                    CONF_CLIENT_ID, default=current.get(CONF_CLIENT_ID, "")
                ): cv.string,
                vol.Optional(
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
