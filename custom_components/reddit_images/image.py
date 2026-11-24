"""Image platform for Reddit Images."""
from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import aiohttp

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.issue_registry import IssueSeverity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    API_URL,
    ARCHIVE_FIELDS,
    ARCHIVE_LIMIT,
    ARCHIVE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_INTERVAL,
    CONF_LIMIT,
    CONF_SELECTION_MODE,
    CONF_SOURCE,
    CONF_SUBREDDIT,
    DEFAULT_INTERVAL,
    DEFAULT_SELECTION_MODE,
    DEFAULT_SOURCE,
    DOMAIN,
    MODE_TOP,
    SOURCE_ARCHIVE,
    SOURCE_REDDIT,
    TOKEN_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
IMAGE_HOSTS = ("i.redd.it", "preview.redd.it", "external-preview.redd.it")

RETRY_DELAYS = (2, 5)
MAX_CACHE_BYTES = 4 * 1024 * 1024


async def _async_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    error_message: str = "Error requesting %s",
    **kwargs: Any,
) -> aiohttp.ClientResponse | None:
    """Send a request, retrying transient network failures only."""
    total = max(attempts, 1)
    for attempt in range(total):
        try:
            return await session.request(method, url, **kwargs)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            if attempt == total - 1:
                _LOGGER.error(error_message, err)
                return None
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            _LOGGER.debug(
                "Transient network error requesting %s (attempt %s of %s): %s",
                url,
                attempt + 1,
                total,
                err,
            )
            await asyncio.sleep(delay)
    return None


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
                config.get(CONF_SOURCE, DEFAULT_SOURCE),
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
        source: str,
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
        self._source = source
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
        self._auth_issue_active = False
        self._fallback_logged = False
        self._failed_urls: set[str] = set()
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"{DOMAIN}.{self._entry_id}"
        )

    @property
    def _has_credentials(self) -> bool:
        """Return True when a Reddit app client ID and secret are set."""
        return bool(self._client_id and self._client_secret)

    async def async_added_to_hass(self) -> None:
        """Start the timer when added to HA."""
        await super().async_added_to_hass()
        await self._async_load_cache()
        if not self._has_credentials and self._source == SOURCE_REDDIT:
            _LOGGER.error(
                "Reddit Images is set to use the Reddit API for r/%s but no client ID "
                "or secret is saved. Open the integration's Configure dialog and add "
                "them, or switch the data source to the archive",
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

    async def _async_load_cache(self) -> None:
        """Restore the last saved image, if any."""
        try:
            cached = await self._store.async_load()
        except Exception as err:
            _LOGGER.debug("Error loading cached Reddit image: %s", err)
            return

        if not isinstance(cached, dict):
            return

        url = cached.get("url")
        encoded = cached.get("image_b64")
        if not url or not encoded:
            return

        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError) as err:
            _LOGGER.debug("Error decoding cached Reddit image: %s", err)
            return

        self._current_image_url = url
        self._current_image_bytes = image_bytes
        self._attr_content_type = cached.get("content_type") or _content_type(
            image_bytes
        )
        last_updated = cached.get("last_updated")
        self._last_image_update = (
            dt_util.parse_datetime(last_updated)
            if isinstance(last_updated, str)
            else None
        ) or dt_util.utcnow()
        self.async_write_ha_state()

    async def _async_save_cache(self, image_bytes: bytes) -> None:
        """Persist the current image so it survives a restart."""
        if not self._current_image_url:
            return

        payload = {
            "url": self._current_image_url,
            "content_type": self._attr_content_type,
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
            "last_updated": dt_util.utcnow().isoformat(),
        }
        if len(json.dumps(payload)) > MAX_CACHE_BYTES:
            _LOGGER.debug(
                "Skipping cached Reddit image for r/%s: payload is larger than 4 MB",
                self._subreddit,
            )
            return

        try:
            await self._store.async_save(payload)
        except Exception as err:
            _LOGGER.debug("Error saving cached Reddit image: %s", err)

    def _report_invalid_auth(self) -> None:
        """Raise a Repairs issue for rejected app credentials."""
        if self._auth_issue_active:
            return
        self._auth_issue_active = True
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"invalid_auth_{self._entry_id}",
            is_fixable=False,
            severity=IssueSeverity.WARNING,
            translation_key="invalid_auth",
            translation_placeholders={"subreddit": self._subreddit},
        )

    def _clear_invalid_auth(self) -> None:
        """Remove the Repairs issue after a successful token request."""
        self._auth_issue_active = False
        ir.async_delete_issue(self.hass, DOMAIN, f"invalid_auth_{self._entry_id}")

    async def _async_get_access_token(self) -> str | None:
        """Return a valid OAuth token, refreshing it when needed."""
        now = dt_util.utcnow()
        if self._access_token and self._token_expires and now < self._token_expires:
            return self._access_token

        session = async_get_clientsession(self.hass)
        response = await _async_request(
            session,
            "post",
            TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(self._client_id, self._client_secret),
            headers={"User-Agent": USER_AGENT},
            error_message="Error requesting a Reddit access token: %s",
        )
        if response is None:
            return None

        try:
            async with response:
                if response.status != 200:
                    body = await response.text()
                    _LOGGER.error(
                        "Reddit rejected the app credentials (%s): %s",
                        response.status,
                        body[:200],
                    )
                    if response.status in (401, 403):
                        self._report_invalid_auth()
                    return None
                self._clear_invalid_auth()
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
        """Return candidate posts from the configured source."""
        if self._source == SOURCE_ARCHIVE:
            self._clear_invalid_auth()
            return await self._async_fetch_archive()

        if self._has_credentials:
            children = await self._async_fetch_reddit()
            if children:
                return children
            if self._source == SOURCE_REDDIT:
                return children
            if not self._fallback_logged:
                self._fallback_logged = True
                _LOGGER.warning(
                    "Reddit did not return posts for r/%s, so the Arctic Shift "
                    "archive is used instead",
                    self._subreddit,
                )
        else:
            self._clear_invalid_auth()

        return await self._async_fetch_archive()

    async def _async_fetch_reddit(self) -> list[dict] | None:
        """Fetch the top posts of the day through the Reddit OAuth API."""
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
        error_message = f"Error fetching r/{self._subreddit} from Reddit: %s"

        for attempt in range(2):
            response = await _async_request(
                session,
                "get",
                url,
                params=params,
                headers=headers,
                error_message=error_message,
            )
            if response is None:
                return None
            try:
                async with response:
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
                _LOGGER.error(error_message, err)
                return None

            return payload.get("data", {}).get("children", [])

        return None

    async def _async_fetch_archive(self) -> list[dict] | None:
        """Fetch recent posts from the Arctic Shift archive.

        The archive needs no account and keeps working when Reddit rejects an
        app, so it is the default when no approved Reddit app is available.
        Scores are only settled for older posts; recent ones may still read 1.
        """
        session = async_get_clientsession(self.hass)
        params = {
            "subreddit": self._subreddit,
            "limit": ARCHIVE_LIMIT,
            "sort": "desc",
            "fields": ARCHIVE_FIELDS,
        }
        response = await _async_request(
            session,
            "get",
            ARCHIVE_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            error_message=(
                f"Error fetching r/{self._subreddit} from the Arctic Shift archive: %s"
            ),
        )
        if response is None:
            return None

        try:
            async with response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Arctic Shift returned %s for r/%s",
                        response.status,
                        self._subreddit,
                    )
                    return None
                payload = await response.json()
        except Exception as err:
            _LOGGER.error("Error reading the Arctic Shift response: %s", err)
            return None

        posts = [post for post in payload.get("data") or [] if isinstance(post, dict)]
        if not posts:
            return []
        posts.sort(key=lambda post: post.get("score") or 0, reverse=True)
        return [{"data": post} for post in posts]

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
        if now is not None:
            # A scheduled refresh starts with a clean slate.
            self._failed_urls.clear()

        children = await self._async_fetch_listing()
        if children is None:
            return

        urls = []
        for child in children:
            post = child.get("data") or {}
            if post.get("stickied"):
                continue
            url = self._best_image_url(post)
            if url and url not in urls and url not in self._failed_urls:
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

    async def _async_download(self, url: str) -> bytes | None:
        """Download one image and cache its bytes."""
        session = async_get_clientsession(self.hass)
        response = await _async_request(
            session,
            "get",
            url,
            headers={"User-Agent": USER_AGENT},
            attempts=2,
            error_message="Error downloading Reddit image: %s",
        )
        if response is None:
            return None

        try:
            async with response:
                if response.status == 200:
                    image_bytes = await response.read()
                    self._current_image_bytes = image_bytes
                    self._attr_content_type = _content_type(image_bytes)
                    await self._async_save_cache(image_bytes)
                    return image_bytes
                _LOGGER.warning(
                    "Reddit image download failed with %s: %s", response.status, url
                )
        except Exception as err:
            _LOGGER.error("Error downloading Reddit image: %s", err)

        return None

    async def async_image(self) -> bytes | None:
        """Return image bytes, moving on when a post's image is gone."""
        if self._current_image_bytes:
            return self._current_image_bytes

        for _ in range(3):
            if not self._current_image_url:
                return None

            url = self._current_image_url
            image_bytes = await self._async_download(url)
            if image_bytes:
                return image_bytes

            # The post may have been removed from Reddit. Try another one.
            self._failed_urls.add(url)
            self._current_image_url = None
            self._current_image_bytes = None
            await self._update_image(None)

        return None

    @property
    def image_last_updated(self) -> datetime | None:
        return self._last_image_update
