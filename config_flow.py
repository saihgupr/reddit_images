"""Config flow for Reddit Images integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, 
    DEFAULT_SUBREDDIT, 
    DEFAULT_LIMIT, 
    DEFAULT_INTERVAL,
    CONF_SUBREDDIT, 
    CONF_LIMIT, 
    CONF_INTERVAL
)

_LOGGER = logging.getLogger(__name__)

# Label for the UI
LABEL_INTERVAL = "Interval (Minutes)"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SUBREDDIT, default=DEFAULT_SUBREDDIT): str,
        vol.Required(CONF_LIMIT, default=DEFAULT_LIMIT): int,
        vol.Required(LABEL_INTERVAL, default=DEFAULT_INTERVAL): int,
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Reddit Images."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Map the UI label back to the internal constant
            val = user_input.pop(LABEL_INTERVAL)
            user_input[CONF_INTERVAL] = val
            
            return self.async_create_entry(title=user_input[CONF_SUBREDDIT], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
