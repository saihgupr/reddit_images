"""Constants for the Reddit Images integration."""

DOMAIN = "reddit_images"
CONF_SUBREDDIT = "subreddit"
CONF_LIMIT = "limit"
CONF_INTERVAL = "interval"
CONF_SELECTION_MODE = "selection_mode"
CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_SOURCE = "source"

# Where the post listings come from
SOURCE_AUTO = "auto"
SOURCE_REDDIT = "reddit"
SOURCE_ARCHIVE = "archive"
DEFAULT_SOURCE = SOURCE_AUTO

# Selection mode options
MODE_RANDOM = "random"
MODE_TOP = "top"

DEFAULT_SUBREDDIT = "rarepuppers"
DEFAULT_LIMIT = 20
DEFAULT_INTERVAL = 60
DEFAULT_SELECTION_MODE = MODE_RANDOM

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_URL = "https://oauth.reddit.com"
USER_AGENT = "python:homeassistant.reddit_images:v1.3 (by /u/reddit_images)"

# Community archive of Reddit posts, used when no approved Reddit app is
# available. It needs no account and no credentials.
ARCHIVE_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"
ARCHIVE_LIMIT = 100
ARCHIVE_FIELDS = (
    "id,title,score,created_utc,url,over_18,post_hint,num_comments,author"
)
