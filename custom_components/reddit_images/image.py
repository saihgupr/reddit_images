"""Image platform for Reddit Images."""
from __future__ import annotations

import html
import logging
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse

import aiohttp

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    API_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INTERVAL,
    CONF_LIMIT,
    CONF_SELECTION_MODE,
    CONF_SUBREDDIT,
    DEFAULT_INTERVAL,
    DEFAULT_SELECTION_MODE,
    MODE_TOP,
    TOKEN_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
IMAGE_HOSTS = ("i.redd.it", "preview.redd.it", "external-preview.redd.it")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Reddit Images based on a config entry."""
    config = {**entry.data, **entry.options}

    async_add_entities(
        [
            RedditImageEntity(
                hass,
                config[CONF_SUBREDDIT],
                config.get(CONF_LIMIT, 20),
                config.get(CONF_INTERVAL, DEFAULT_INTERVAL),
                config.get(CONF_SELECTION_MODE, DEFAULT_SELECTION_MODE),
                config.get(CONF_CLIENT_ID, ""),
                config.get(CONF_CLIENT_SECRET, ""),
                entry.entry_id,
            )
        ],
        True,
    )


def _looks_like_image(url: str) -> bool:
    """Return True if the URL points at a directly usable image."""
    if not url:
        return False
    clean = html.unescape(url)
    host = (urlparse(clean).hostname or "").lower()
    if any(host == candidate or host.endswith(f".{candidate}") for candidate in IMAGE_HOSTS):
        return True
    return clean.split("?")[0].lower().endswith(IMAGE_EXTENSIONS)


def _content_type(image_bytes: bytes) -> str:
    """Guess the content type from the image header."""
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"GIF8"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


class RedditImageEntity(ImageEntity):
    """Representation of a Reddit Image."""

    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        subreddit: str,
        limit: int,
        interval: int,
        selection_mode: str,
        client_id: str,
        client_secret: str,
        entry_id: str,
    ) -> None:
        """Initialize the image entity."""
        super().__init__(hass)
        self._subreddit = subreddit
        self._limit = limit
        self._interval = interval
        self._selection_mode = selection_mode
        self._client_id = client_id
        self._client_secret = client_secret
        self._entry_id = entry_id

        self._attr_name = f"Reddit Images {subreddit}"
        self._attr_unique_id = f"{entry_id}_image"
        self._attr_content_type = "image/jpeg"
        self._attr_icon = "mdi:reddit"

        self._access_token: str | None = None
        self._token_expires: datetime | None = None
        self._current_image_url: str | None = None
        self._current_image_bytes: bytes | None = None
        self._last_image_update: datetime | None = None
        self._remove_update_listener = None

    async def async_added_to_hass(self) -> None:
        """Start the timer when added to HA."""
        await super().async_added_to_hass()
        if not self._client_id or not self._client_secret:
            _LOGGER.error(
                "Reddit Images needs a Reddit app client ID and secret for r/%s. "
                "Open the integration's Configure dialog and add them",
                self._subreddit,
            )
            return
        await self._update_image(None)
        self._remove_update_listener = async_track_time_interval(
            self.hass,
            self._update_image,
            timedelta(minutes=self._interval),
        )

    async def async_will_remove_from_hass(self) -> None:
        """Stop the timer when removed."""
        if self._remove_update_listener:
            self._remove_update_listener()
            self._remove_update_listener = None
        await super().async_will_remove_from_hass()

    async def _async_get_access_token(self) -> str | None:
        """Return a valid OAuth token, refreshing it when needed."""
        now = dt_util.utcnow()
        if self._access_token and self._token_expires and now < self._token_expires:
            return self._access_token

        session = async_get_clientsession(self.hass)
        try:
            async with session.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(self._client_id, self._client_secret),
                headers={"User-Agent": USER_AGENT},
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    _LOGGER.error(
                        "Reddit rejected the app credentials (%s): %s",
                        response.status,
                        body[:200],
                    )
                    return None
                payload = await response.json()
        except Exception as err:
            _LOGGER.error("Error requesting a Reddit access token: %s", err)
            return None

        token = payload.get("access_token")
        if not token:
            _LOGGER.error("Reddit token response did not contain an access token")
            return None

        expires_in = int(payload.get("expires_in", 3600))
        self._access_token = token
        self._token_expires = now + timedelta(seconds=max(expires_in - 60, 60))
        return token

    async def _async_fetch_listing(self) -> list[dict] | None:
        """Fetch the top posts of the day for the subreddit."""
        token = await self._async_get_access_token()
        if not token:
            return None

        url = f"{API_URL}/r/{self._subreddit}/top"
        params = {"t": "day", "limit": min(max(self._limit, 1), 100), "raw_json": 1}
        headers = {
            "User-Agent": USER_AGENT,
            "Authorization": f"bearer {token}",
        }
        session = async_get_clientsession(self.hass)

        for attempt in range(2):
            try:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 401 and attempt == 0:
                        self._access_token = None
                        self._token_expires = None
                        token = await self._async_get_access_token()
                        if not token:
                            return None
                        headers["Authorization"] = f"bearer {token}"
                        continue
                    if response.status != 200:
                        _LOGGER.warning(
                            "Reddit error %s for r/%s", response.status, self._subreddit
                        )
                        return None
                    payload = await response.json()
            except Exception as err:
                _LOGGER.error("Error fetching r/%s from Reddit: %s", self._subreddit, err)
                return None

            return payload.get("data", {}).get("children", [])

        return None

    def _best_image_url(self, post: dict) -> str | None:
        """Pick the highest resolution image URL from a post."""
        if post.get("over_18"):
            return None

        if post.get("is_gallery"):
            metadata = post.get("media_metadata") or {}
            items = (post.get("gallery_data") or {}).get("items") or []
            for item in items:
                source = (metadata.get(item.get("media_id")) or {}).get("s") or {}
                if source.get("u"):
                    return html.unescape(source["u"])

        direct = post.get("url_overridden_by_dest") or post.get("url")
        if direct and _looks_like_image(direct):
            return html.unescape(direct)

        for image in (post.get("preview") or {}).get("images") or []:
            source = (image.get("source") or {}).get("url")
            if source and _looks_like_image(source):
                return html.unescape(source)

        thumbnail = post.get("thumbnail")
        if thumbnail and thumbnail.startswith("http"):
            return html.unescape(thumbnail)

        return None

    async def _update_image(self, now) -> None:
        """Pick a new image from the subreddit's top posts."""
        children = await self._async_fetch_listing()
        if children is None:
            return

        urls = []
        for child in children:
            post = child.get("data") or {}
            if post.get("stickied"):
                continue
            url = self._best_image_url(post)
            if url and url not in urls:
                urls.append(url)

        if not urls:
            _LOGGER.warning(
                "No valid images found in top %s posts of r/%s",
                self._limit,
                self._subreddit,
            )
            return

        new_url = urls[0] if self._selection_mode == MODE_TOP else random.choice(urls)
        if new_url != self._current_image_url:
            self._current_image_url = new_url
            self._current_image_bytes = None
        self._last_image_update = dt_util.utcnow()
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        """Return bytes of image."""
        if not self._current_image_url:
            return None

        if self._current_image_bytes:
            return self._current_image_bytes

        headers = {"User-Agent": USER_AGENT}
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(self._current_image_url, headers=headers) as response:
                if response.status == 200:
                    image_bytes = await response.read()
                    self._current_image_bytes = image_bytes
                    self._attr_content_type = _content_type(image_bytes)
                    return image_bytes
                _LOGGER.warning(
                    "Reddit image download failed with %s: %s",
                    response.status,
                    self._current_image_url,
                )
        except Exception as err:
            _LOGGER.error("Error downloading Reddit image: %s", err)

        return None

    @property
    def image_last_updated(self) -> datetime | None:
        return self._last_image_update
