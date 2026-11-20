"""Constants for the Reddit Images integration."""

DOMAIN = "reddit_images"
CONF_SUBREDDIT = "subreddit"
CONF_LIMIT = "limit"
CONF_INTERVAL = "interval"
CONF_SELECTION_MODE = "selection_mode"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"

# Selection mode options
MODE_RANDOM = "random"
MODE_TOP = "top"

DEFAULT_SUBREDDIT = "rarepuppers"
DEFAULT_LIMIT = 20
DEFAULT_INTERVAL = 60
DEFAULT_SELECTION_MODE = MODE_RANDOM

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_URL = "https://oauth.reddit.com"
USER_AGENT = "python:homeassistant.reddit_images:v1.0.11 (by /u/reddit_images)"
