"""Image: what each tag shows, drawn by the AP (GET /api/tags/{mac}/image), as a PNG.

The AP draws the image on each request, so it is fetched only when the tag's content or
its drawing changed (content_id, image_id, model, content_error), and only when something asks for it
(a card that is open); the PNG is kept until the next change.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import struct
from typing import Any
import zlib

from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import OpenEslApiError, OpenEslError
from .coordinator import OpenEslConfigEntry, OpenEslCoordinator, tag_source
from .entity import OpenEslTagEntity, setup_tag_platform

PARALLEL_UPDATES = 1

SCREEN = ImageEntityDescription(key="screen", translation_key="screen")

# White, black, red: the PNG's palette, indexed by the pixel value
PALETTE = bytes((255, 255, 255, 0, 0, 0, 204, 0, 0))


def screen_key(tag: dict[str, Any]) -> tuple[Any, ...] | None:
    """What the drawn image depends on; None: nothing to show (no content yet)."""
    if not tag.get("content_id"):
        return None
    # content_error: a 409 for a layout not in the file stands until the AP clears it at a
    # later poll, which it does without a new content_id
    return (tag.get("content_id"), tag.get("image_id"), tag.get("model"), tag.get("content_error"))


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def tag_image_png(reply: dict[str, Any]) -> bytes | None:
    """GET /api/tags/{mac}/image as a PNG; None when the reply is short or malformed.

    `data` is the black plane, then the red plane when `red`: `width` columns from left to
    right, each ceil(height / 8) bytes, byte 0 bit 7 the top row, a set bit is ink.
    """
    try:
        width, height, red = int(reply["width"]), int(reply["height"]), bool(reply["red"])
        data = base64.b64decode(reply["data"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error):
        return None
    col = (height + 7) // 8
    plane = width * col
    if width <= 0 or height <= 0 or len(data) < plane * (2 if red else 1):
        return None

    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter: none
        byte, mask = y >> 3, 0x80 >> (y & 7)
        for x in range(width):
            i = x * col + byte
            if red and data[plane + i] & mask:
                rows.append(2)
            elif data[i] & mask:
                rows.append(1)
            else:
                rows.append(0)

    return (
        b"\x89PNG\r\n\x1a\n"
        # 8-bit palette colour
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
        + _chunk(b"PLTE", PALETTE if red else PALETTE[:6])
        + _chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + _chunk(b"IEND", b"")
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenEslConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    setup_tag_platform(
        hass,
        entry,
        async_add_entities,
        lambda coordinator, mac: [TagScreen(coordinator, mac)],
    )


class TagScreen(OpenEslTagEntity, ImageEntity):
    """The tag's screen. Empty before the tag has content, or when the AP cannot draw it."""

    _attr_content_type = "image/png"
    entity_description = SCREEN

    def __init__(self, coordinator: OpenEslCoordinator, mac: str) -> None:
        OpenEslTagEntity.__init__(self, coordinator, mac, SCREEN.key)
        ImageEntity.__init__(self, coordinator.hass)
        # self.tag needs hass, which is set when the entity is added: ask the AP that heard
        # the tag last here too
        source = tag_source(coordinator.hass, mac) or coordinator
        self._key = screen_key(source.data.tags.get(mac, {}))
        self._png: bytes | None = None
        # The key of the PNG above, or of a reply that stands until the key changes (4xx)
        self._png_key: tuple[Any, ...] | None = None
        # The last image the AP drew, shown while it cannot draw the new one (429, 503,
        # no answer) instead of a broken image
        self._last_png: bytes | None = None
        # One request at a time: two cards open right after a change draw it once on the AP
        self._lock = asyncio.Lock()
        self._attr_image_last_updated = dt_util.utcnow() if self._key else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tag = self.tag
        return {
            "content_id": tag.get("content_id"),
            # The tag does not show this image yet
            "pending": tag.get("pending"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        key = screen_key(self.tag)
        if key != self._key:
            self._key = key
            self._attr_image_last_updated = dt_util.utcnow() if key else None
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        async with self._lock:
            return await self._fetch()

    async def _fetch(self) -> bytes | None:
        key = self._key
        if key is None:
            return None
        if key == self._png_key:
            return self._png
        try:
            reply = await self.source.api.get_tag_image(self.mac)
        except OpenEslApiError as err:
            # 404: no content or model yet; 409: content the AP cannot draw. Both stand
            # until the content changes. 429 and 503 (no memory) are asked again.
            if 400 <= err.status < 500 and err.status != 429:
                self._png, self._png_key = None, key
                # An older image is not what the tag has now: nothing to fall back to
                self._last_png = None
                return None
            return self._last_png
        except OpenEslError:
            return self._last_png
        png = tag_image_png(reply)
        # The tag may have got new content while the AP drew this one: keep it for its key
        if png is not None and reply.get("content_id") == key[0]:
            self._png, self._png_key = png, key
        if png is not None:
            self._last_png = png
        return png if png is not None else self._last_png
