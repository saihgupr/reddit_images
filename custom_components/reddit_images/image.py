"""Image platform for Reddit Images."""
import logging
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import CONF_SUBREDDIT, CONF_LIMIT, CONF_INTERVAL, CONF_SELECTION_MODE, DEFAULT_INTERVAL, DEFAULT_SELECTION_MODE, MODE_TOP

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
    selection_mode = entry.data.get(CONF_SELECTION_MODE, DEFAULT_SELECTION_MODE)

    async_add_entities([RedditImageEntity(hass, subreddit, limit, interval, selection_mode, entry.entry_id)], True)


class RedditImageEntity(ImageEntity):
    """Representation of a Reddit Image."""
    
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, subreddit: str, limit: int, interval: int, selection_mode: str, entry_id: str) -> None:
        """Initialize the image entity."""
        super().__init__(hass)
        self._subreddit = subreddit
        self._limit = limit
        self._interval = interval
        self._selection_mode = selection_mode
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
        url = f"https://www.reddit.com/r/{self._subreddit}/top.rss?t=day"
        
        # Reddit requires a specific User-Agent format to not block scripts
        # Format: <platform>:<app ID>:<version string> (by /u/<reddit username>)
        headers = {"User-Agent": "python:homeassistant.reddit_images:v2.0.0 (by /u/homeassistant_user)"}
        
        session = async_get_clientsession(self.hass)
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    xml_content = await response.text()
                    try:
                        root = ET.fromstring(xml_content)
                    except ET.ParseError as parse_err:
                        _LOGGER.error("Error parsing Reddit RSS XML: %s", parse_err)
                        return
                    
                    ns = {
                        'atom': 'http://www.w3.org/2005/Atom',
                        'media': 'http://search.yahoo.com/mrss/'
                    }
                    entries = root.findall('atom:entry', ns)
                    
                    valid_posts = []
                    for entry in entries:
                        content_elem = entry.find('atom:content', ns)
                        content_html = content_elem.text if content_elem is not None else ""
                        
                        src_urls = re.findall(r'<img[^>]+src="([^"]+)"', content_html)
                        href_urls = re.findall(r'<a[^>]+href="([^"]+)"', content_html)
                        
                        best_image = None
                        
                        # Look at hrefs first (usually high-resolution direct links)
                        for href in href_urls:
                            href_clean = href.replace("&amp;", "&")
                            if "i.redd.it" in href_clean or href_clean.split('?')[0].lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                                best_image = href_clean
                                break
                        
                        # If no direct link, use image src (usually preview/thumbnail)
                        if not best_image:
                            for src in src_urls:
                                src_clean = src.replace("&amp;", "&")
                                if "preview.redd.it" in src_clean or "external-preview.redd.it" in src_clean or src_clean.split('?')[0].lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                                    best_image = src_clean
                                    break
                                    
                        if best_image:
                            valid_posts.append(best_image)
                    
                    valid_posts = valid_posts[:self._limit]
                    
                    if valid_posts:
                        # Top mode: always use highest upvoted (first in list)
                        # Random mode: pick randomly from top posts for variety
                        new_url = valid_posts[0] if self._selection_mode == MODE_TOP else random.choice(valid_posts)
                        # We force update if we found anything, even if it's the same URL, 
                        # to ensure the timestamp updates and demonstrates "activity"
                        self._current_image_url = new_url
                        # Don't download bytes yet; async_image will do it
                        self._current_image_bytes = None 
                        self._last_image_update = dt_util.utcnow()
                        self.async_write_ha_state()
                    else:
                          _LOGGER.warning("No valid images found in top %s posts of r/%s", self._limit, self._subreddit)
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
            
        headers = {"User-Agent": "python:homeassistant.reddit_images:v2.0.0 (by /u/homeassistant_user)"}
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(self._current_image_url, headers=headers) as response:
                if response.status == 200:
                    self._current_image_bytes = await response.read()
                    return self._current_image_bytes
        except Exception:
            pass
        return None
    
    @property
    def image_last_updated(self) -> datetime | None:
        return self._last_image_update
