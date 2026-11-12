"""The Screen image entity: GET /api/tags/{mac}/image as a PNG, fetched only when it changed."""

import asyncio
import base64
from http import HTTPStatus
import struct
from unittest.mock import patch
import zlib

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.image import DOMAIN as IMAGE_DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.openesl.image import tag_image_png

from conftest import AP, HEALTH, MAC1, MAC2, TAGS, URL, WIFI, tag

SCREEN1 = "image.tag_01234567_screen"
SCREEN2 = "image.tag_02066346_screen"


def _planes(pixels, red):
    """pixels (rows of 0 white, 1 black, 2 red) as the AP's bit planes, base64."""
    height, width = len(pixels), len(pixels[0])
    col = (height + 7) // 8
    black, redp = bytearray(width * col), bytearray(width * col)
    for y, row in enumerate(pixels):
        for x, v in enumerate(row):
            i, m = x * col + (y >> 3), 0x80 >> (y & 7)
            if v == 1:
                black[i] |= m
            elif v == 2:
                redp[i] |= m
    return base64.b64encode(bytes(black) + (bytes(redp) if red else b"")).decode()


def _reply(mac, pixels, red=False, content_id=2914470401, image_id=3522432519):
    return {
        "mac": mac,
        "model": "2.9",
        "width": len(pixels[0]),
        "height": len(pixels),
        "red": red,
        "content_id": content_id,
        "image_id": image_id,
        "data": _planes(pixels, red),
    }


def _decode_png(png):
    """(width, height, palette, rows of palette indices) of an 8-bit palette PNG."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, {}
    while pos < len(png):
        (n,) = struct.unpack(">I", png[pos : pos + 4])
        kind, data = png[pos + 4 : pos + 8], png[pos + 8 : pos + 8 + n]
        assert struct.unpack(">I", png[pos + 8 + n : pos + 12 + n])[0] == zlib.crc32(kind + data)
        chunks[kind] = chunks.get(kind, b"") + data
        pos += 12 + n
    width, height, depth, ctype = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, ctype) == (8, 3)
    raw = zlib.decompress(chunks[b"IDAT"])
    rows = []
    for y in range(height):
        line = raw[y * (width + 1) : (y + 1) * (width + 1)]
        assert line[0] == 0
        rows.append(list(line[1:]))
    return width, height, chunks[b"PLTE"], rows


# 4 x 10: crosses a byte boundary in a column (height not a multiple of 8)
PIXELS = [[(x + y) % 3 for x in range(4)] for y in range(10)]


def test_png_black_white_red() -> None:
    width, height, palette, rows = _decode_png(tag_image_png(_reply(MAC1, PIXELS, red=True)))
    assert (width, height) == (4, 10)
    assert rows == PIXELS
    assert palette == bytes((255, 255, 255, 0, 0, 0, 204, 0, 0))


def test_png_black_white() -> None:
    # Without a red plane red pixels are white, and the palette has two colours
    _, _, palette, rows = _decode_png(tag_image_png(_reply(MAC1, PIXELS, red=False)))
    assert rows == [[v if v == 1 else 0 for v in row] for row in PIXELS]
    assert len(palette) == 6


def test_png_short_or_broken_reply() -> None:
    reply = _reply(MAC1, PIXELS, red=True)
    assert tag_image_png({**reply, "data": base64.b64encode(b"\0" * 8).decode()}) is None
    assert tag_image_png({**reply, "data": "not base64!"}) is None
    assert tag_image_png({**reply, "width": 0}) is None
    assert tag_image_png({k: v for k, v in reply.items() if k != "red"}) is None


def _image_calls(aioclient_mock, mac):
    return [c for c in aioclient_mock.mock_calls if c[0] == "GET" and str(c[1]) == f"{URL}/api/tags/{mac}/image"]


async def _look(hass, client, entity_id):
    """GET the image as a card does: the image proxy with the entity's access token."""
    token = hass.states.get(entity_id).attributes["access_token"]
    return await client.get(f"/api/image_proxy/{entity_id}?token={token}")


async def _setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_screen_fetched_once_until_it_changes(
    hass: HomeAssistant, ap, entry, hass_client_no_auth, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-07T12:00:00+00:00")
    ap.get(f"{URL}/api/tags/{MAC1}/image", json=_reply(MAC1, PIXELS))
    await _setup(hass, entry)
    state = hass.states.get(SCREEN1)
    assert state.state == "2026-11-07T12:00:00+00:00"
    assert state.attributes["content_id"] == 2914470401
    assert state.attributes["pending"] is False
    # Nothing is fetched before something looks at it
    assert _image_calls(ap, MAC1) == []

    client = await hass_client_no_auth()
    for _ in range(2):
        resp = await _look(hass, client, SCREEN1)
        assert resp.status == HTTPStatus.OK
        assert resp.content_type == "image/png"
        assert _decode_png(await resp.read())[3] == [[v if v == 1 else 0 for v in row] for row in PIXELS]
    assert len(_image_calls(ap, MAC1)) == 1

    # A poll with the same content: the image stays, no new request
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(SCREEN1).state == "2026-11-07T12:00:00+00:00"
    await _look(hass, client, SCREEN1)
    assert len(_image_calls(ap, MAC1)) == 1

    # New content: a new image, fetched once more
    ap.clear_requests()
    new = [[1 - v % 2 for v in row] for row in PIXELS]
    ap.get(f"{URL}/api/tags", json={"ap": AP, "tags": [tag(MAC1, content_id=7, image_id=8, pending=True), TAGS["tags"][1]]})
    ap.get(f"{URL}/api/health", json=HEALTH)
    ap.get(f"{URL}/api/wifi", json=WIFI)
    ap.get(f"{URL}/api/remote", status=404, json={"error": "not found"})
    ap.get(f"{URL}/api/tags/{MAC1}/image", json=_reply(MAC1, new, content_id=7, image_id=8))
    freezer.tick(120)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(SCREEN1)
    assert state.state == "2026-11-07T12:04:00+00:00"
    assert state.attributes["pending"] is True
    resp = await _look(hass, client, SCREEN1)
    assert _decode_png(await resp.read())[3] == new
    assert len(_image_calls(ap, MAC1)) == 1


async def test_screen_ap_cannot_draw(hass: HomeAssistant, ap, entry, hass_client_no_auth) -> None:
    """409 (content_error) and 404: empty, and not asked again until the content changes."""
    ap.get(f"{URL}/api/tags/{MAC1}/image", status=409, json={"error": "layout not found"})
    await _setup(hass, entry)
    client = await hass_client_no_auth()
    for _ in range(2):
        resp = await _look(hass, client, SCREEN1)
        assert resp.status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert len(_image_calls(ap, MAC1)) == 1


async def test_screen_ap_busy_asked_again(hass: HomeAssistant, ap, entry, hass_client_no_auth) -> None:
    """503 (no memory to draw) is not kept: the next look asks again."""
    ap.get(f"{URL}/api/tags/{MAC1}/image", status=503, json={"error": "no memory"})
    await _setup(hass, entry)
    client = await hass_client_no_auth()
    assert (await _look(hass, client, SCREEN1)).status == HTTPStatus.INTERNAL_SERVER_ERROR
    ap.clear_requests()
    ap.get(f"{URL}/api/tags/{MAC1}/image", json=_reply(MAC1, PIXELS))
    assert (await _look(hass, client, SCREEN1)).status == HTTPStatus.OK
    assert len(_image_calls(ap, MAC1)) == 1


async def test_screen_new_tag_without_content(hass: HomeAssistant, aioclient_mock, entry, hass_client_no_auth) -> None:
    """A tag that has polled but has no content yet (content_id 0): no image, no request."""
    aioclient_mock.get(f"{URL}/api/tags", json={"ap": AP, "tags": [tag(MAC2, content_id=0, shown_content_id=0, image_id=None, shown_image_id=0)]})
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    aioclient_mock.get(f"{URL}/api/remote", status=404, json={"error": "not found"})
    await _setup(hass, entry)
    assert hass.states.get(SCREEN2).state == "unknown"
    client = await hass_client_no_auth()
    assert (await _look(hass, client, SCREEN2)).status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert _image_calls(aioclient_mock, MAC2) == []


def _poll(aioclient_mock, *tags):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/tags", json={"ap": AP, "tags": list(tags)})
    aioclient_mock.get(f"{URL}/api/health", json=HEALTH)
    aioclient_mock.get(f"{URL}/api/wifi", json=WIFI)
    aioclient_mock.get(f"{URL}/api/remote", status=404, json={"error": "not found"})


async def _refresh(hass):
    await hass.services.async_call("openesl", "refresh", {}, blocking=True)
    await hass.async_block_till_done()


async def test_screen_two_looks_at_once_draw_once(hass: HomeAssistant, ap, entry) -> None:
    """Two cards that open together right after a change: the AP draws the image once."""
    await _setup(hass, entry)
    screen = hass.data[IMAGE_DOMAIN].get_entity(SCREEN1)
    calls = 0

    async def slow_image(mac):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return _reply(MAC1, PIXELS)

    with patch.object(entry.runtime_data.api, "get_tag_image", slow_image):
        first, second = await asyncio.gather(screen.async_image(), screen.async_image())
    assert first == second and first is not None
    assert calls == 1


async def test_screen_content_error_cleared(hass: HomeAssistant, ap, entry, hass_client_no_auth) -> None:
    """A 409 for a layout not in the file is asked again once the AP clears content_error,
    which it does without a new content_id."""
    _poll(ap, tag(MAC1, content_error="layout"), TAGS["tags"][1])
    ap.get(f"{URL}/api/tags/{MAC1}/image", status=409, json={"error": "layout not in file"})
    await _setup(hass, entry)
    client = await hass_client_no_auth()
    assert (await _look(hass, client, SCREEN1)).status == HTTPStatus.INTERNAL_SERVER_ERROR

    _poll(ap, TAGS["tags"][0], TAGS["tags"][1])
    ap.get(f"{URL}/api/tags/{MAC1}/image", json=_reply(MAC1, PIXELS))
    await _refresh(hass)
    assert (await _look(hass, client, SCREEN1)).status == HTTPStatus.OK
    assert len(_image_calls(ap, MAC1)) == 1


async def test_screen_busy_keeps_last_image(hass: HomeAssistant, ap, entry, hass_client_no_auth) -> None:
    """New content the AP cannot draw just now (503): the card keeps the last image instead of
    a broken one, and the next look asks again."""
    ap.get(f"{URL}/api/tags/{MAC1}/image", json=_reply(MAC1, PIXELS))
    await _setup(hass, entry)
    client = await hass_client_no_auth()
    before = await (await _look(hass, client, SCREEN1)).read()

    _poll(ap, tag(MAC1, content_id=7, image_id=8), TAGS["tags"][1])
    ap.get(f"{URL}/api/tags/{MAC1}/image", status=503, json={"error": "no memory"})
    await _refresh(hass)
    resp = await _look(hass, client, SCREEN1)
    assert resp.status == HTTPStatus.OK
    assert await resp.read() == before
    assert len(_image_calls(ap, MAC1)) == 1

    new = [[1] * 4 for _ in range(10)]
    _poll(ap, tag(MAC1, content_id=7, image_id=8), TAGS["tags"][1])
    ap.get(f"{URL}/api/tags/{MAC1}/image", json=_reply(MAC1, new, content_id=7, image_id=8))
    assert _decode_png(await (await _look(hass, client, SCREEN1)).read())[3] == new


async def test_screen_no_fallback_past_a_409(hass: HomeAssistant, ap, entry, hass_client_no_auth) -> None:
    """A drawn, then B the AP cannot draw (409), then C while it is busy (503): empty, not A."""
    ap.get(f"{URL}/api/tags/{MAC1}/image", json=_reply(MAC1, PIXELS))
    await _setup(hass, entry)
    client = await hass_client_no_auth()
    assert (await _look(hass, client, SCREEN1)).status == HTTPStatus.OK

    _poll(ap, tag(MAC1, content_id=7, image_id=8), TAGS["tags"][1])
    ap.get(f"{URL}/api/tags/{MAC1}/image", status=409, json={"error": "cannot draw"})
    await _refresh(hass)
    assert (await _look(hass, client, SCREEN1)).status == HTTPStatus.INTERNAL_SERVER_ERROR

    _poll(ap, tag(MAC1, content_id=9, image_id=10), TAGS["tags"][1])
    ap.get(f"{URL}/api/tags/{MAC1}/image", status=503, json={"error": "no memory"})
    await _refresh(hass)
    assert (await _look(hass, client, SCREEN1)).status == HTTPStatus.INTERNAL_SERVER_ERROR
