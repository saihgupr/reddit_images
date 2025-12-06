"""Image platform for Reddit Images."""
import logging
import random
from datetime import datetime, timedelta

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import CONF_SUBREDDIT, CONF_LIMIT, CONF_INTERVAL, DEFAULT_INTERVAL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Reddit Images based on a config entry."""
    subreddit = entry.data[CONF_SUBREDDIT]
    limit = entry.data[CONF_LIMIT]
    interval = entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL)

    async_add_entities([RedditImageEntity(hass, subreddit, limit, interval, entry.entry_id)], True)


class RedditImageEntity(ImageEntity):
    """Representation of a Reddit Image."""
    
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, subreddit: str, limit: int, interval: int, entry_id: str) -> None:
        """Initialize the image entity."""
        super().__init__(hass)
        self._subreddit = subreddit
        self._limit = limit
        self._interval = interval
        self._entry_id = entry_id
        
        self._attr_name = f"Reddit Images {subreddit}"
        self._attr_unique_id = f"{entry_id}_image"
        # Used by HA to know what to expect
        self._attr_content_type = "image/jpeg"
        self._attr_icon = "mdi:reddit"
        
        self._current_image_url = None
        self._current_image_bytes = None
        self._last_image_update = None
        self._remove_update_listener = None

    async def async_added_to_hass(self) -> None:
        """Start the timer when added to HA."""
        await super().async_added_to_hass()
        # Initial update
        await self._update_image(None)
        # Schedule updates
        self._remove_update_listener = async_track_time_interval(
            self.hass,
            self._update_image,
            timedelta(minutes=self._interval)
        )
        
    async def async_will_remove_from_hass(self) -> None:
        """Stop the timer when removed."""
        if self._remove_update_listener:
            self._remove_update_listener()
            self._remove_update_listener = None
        await super().async_will_remove_from_hass()

    async def _update_image(self, now) -> None:
        """Fetch new image URL from Reddit."""
        url = f"https://www.reddit.com/r/{self._subreddit}/top.json?sort=hot&t=day&limit={self._limit}"
        
        # Reddit requires a specific User-Agent format to not block scripts
        # Format: <platform>:<app ID>:<version string> (by /u/<reddit username>)
        headers = {"User-Agent": "python:homeassistant.reddit_images:v2.0.0 (by /u/homeassistant_user)"}
        
        session = async_get_clientsession(self.hass)
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    children = data.get("data", {}).get("children", [])
                    
                    valid_posts = []
                    for child in children:
                        post = child.get("data", {})
                        post_url = post.get("url", "")
                        # Validate it's an image
                        if post_url.lower().endswith((".jpg", ".jpeg", ".png")):
                            valid_posts.append(post_url)
                    
                    if valid_posts:
                        new_url = random.choice(valid_posts)
                        # We force update if we found anything, even if it's the same URL, 
                        # to ensure the timestamp updates and demonstrates "activity"
                        self._current_image_url = new_url
                        # Don't download bytes yet; async_image will do it
                        self._current_image_bytes = None 
                        self._last_image_update = dt_util.utcnow()
                        self.async_write_ha_state()
                    else:
                         _LOGGER.warning("No valid images (jpg/png) found in top %s posts of r/%s", self._limit, self._subreddit)
                else:
                    _LOGGER.warning("Reddit error %s for r/%s", response.status, self._subreddit)
        except Exception as err:
            _LOGGER.error("Error updating Reddit Image URL: %s", err)

    async def async_image(self) -> bytes | None:
        """Return bytes of image."""
        if not self._current_image_url:
            return None
            
        if self._current_image_bytes:
            return self._current_image_bytes
            
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(self._current_image_url) as response:
                if response.status == 200:
                    self._current_image_bytes = await response.read()
                    return self._current_image_bytes
        except Exception:
            pass
        return None
    
    @property
    def image_last_updated(self) -> datetime | None:
        return self._last_image_update
