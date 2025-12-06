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
    DEFAULT_SELECTION_MODE,
    CONF_SUBREDDIT, 
    CONF_LIMIT, 
    CONF_INTERVAL,
    CONF_SELECTION_MODE,
    MODE_RANDOM,
    MODE_TOP,
)

_LOGGER = logging.getLogger(__name__)

# Labels for the UI
LABEL_INTERVAL = "Interval (Minutes)"
LABEL_SELECTION_MODE = "Selection Mode"

# Human-readable selection mode options
SELECTION_MODE_OPTIONS = {
    MODE_RANDOM: "Random from Top",
    MODE_TOP: "Top Post",
}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SUBREDDIT, default=DEFAULT_SUBREDDIT): str,
        vol.Required(CONF_LIMIT, default=DEFAULT_LIMIT): int,
        vol.Required(LABEL_INTERVAL, default=DEFAULT_INTERVAL): int,
        vol.Required(LABEL_SELECTION_MODE, default=DEFAULT_SELECTION_MODE): vol.In(SELECTION_MODE_OPTIONS),
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
            # Map the UI labels back to the internal constants
            val = user_input.pop(LABEL_INTERVAL)
            user_input[CONF_INTERVAL] = val
            
            mode = user_input.pop(LABEL_SELECTION_MODE)
            user_input[CONF_SELECTION_MODE] = mode
            
            return self.async_create_entry(title=user_input[CONF_SUBREDDIT], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
