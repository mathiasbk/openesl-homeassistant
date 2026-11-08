"""Constants for the OpenESL integration."""

DOMAIN = "openesl"

# How often GET /api/tags is read (the options): with ~200 tags its reply is about 120 KB,
# which a C6 on weak WiFi sends between tag polls, so not every minute by default
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 120
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 3600

# APs set up with firmware 0.6.0 or older are all named "openesl": not an id
LEGACY_HOSTNAME = "openesl"

# PUT /api/tags takes at most 50 rows (RAM on the AP)
BATCH_MAX = 50
# ... and a body of at most 1,024 JSON tokens and 24,576 bytes (openESL openapi.yaml): 50 tags
# with 14 or more fields pass the token limit, so batches are also cut by these (with a margin)
BODY_MAX_TOKENS = 1024 - 3 - 16
BODY_MAX_BYTES = 24576 - 64 - 512
# PUT /api/tags/{mac}/draw: the AP reads the whole body as at most this many JSON values
DRAW_MAX_TOKENS = 1024

ATTR_MAC = "mac"
ATTR_LAYOUT = "layout"
ATTR_FIELDS = "fields"
ATTR_PRICE_HIGHLIGHT = "price_highlight"
ATTR_FRAME = "frame"
ATTR_AT = "at"
ATTR_PATH = "path"
ATTR_DITHER = "dither"
ATTR_ICONS = "icons"

SERVICE_SEND = "send"
SERVICE_SEND_IMAGE = "send_image"
SERVICE_DRAW = "draw"
SERVICE_REFRESH = "refresh"
