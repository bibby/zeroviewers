import os

APP_PHASE = 'beta'
APP_VERSION = '0.4.2, 19 Jun 2016'

LOGIN_ENABLED = bool(int(os.environ.get('LOGIN_ENABLED', 1)))
CONTACT_EMAIL = 'zeroviewsite@gmail.com'
DONATE_URL = 'https://www.paypal.me/protobaggins'
DONATE_SERVICE = 'Paypal'
MAX_VIEWERS = 4
API_MAX_ITEMS = 100
API_DECR = 80
PAGE_MAX_ITEMS = 40

MIN_LIVE_MINUTES = 15
MAX_LIVE_MINUTES = 60 * 9
WORKER_INTERVAL = 60 * 9

# redis keys
CHANNELS = "channels"
CHANNEL_COUNT = "channel_count"
LANGUAGES = "languages"
TOTAL_LIVE = "total_live"
ZERO_VIEWERS = "zero_viewers"
META_DATA = "meta"
GAMES = "games"

# worker signals
SIG_INVALID = 0
SIG_ADDED = 1
SIG_SKIPPED = 2
SIG_OK = 3
