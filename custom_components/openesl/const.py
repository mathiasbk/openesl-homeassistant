"""Constants for the OpenESL integration."""

from datetime import timedelta

DOMAIN = "openesl"

# GET /api/tags once a minute: the tags themselves poll the AP every 60 s by default
SCAN_INTERVAL = timedelta(seconds=60)

# PUT /api/tags takes at most 50 rows (RAM on the AP)
BATCH_MAX = 50

ATTR_MAC = "mac"
ATTR_LAYOUT = "layout"
ATTR_FIELDS = "fields"
ATTR_PRICE_HIGHLIGHT = "price_highlight"
ATTR_FRAME = "frame"
ATTR_AT = "at"
ATTR_PATH = "path"
ATTR_DITHER = "dither"

SERVICE_SEND = "send"
SERVICE_SEND_IMAGE = "send_image"
SERVICE_REFRESH = "refresh"
